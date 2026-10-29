"""Creating, running and serving jobs. A job is one tool, or a workflow of tools chained together."""

import logging
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select

from app.domain.errors import FolioError, Forbidden, NotFound, ValidationFailed
from app.domain.ports import AIProvider, DocumentConverter, FileStorage, JobQueue
from app.engines.ghostscript import Ghostscript
from app.infra.db import Database, Job, as_utc, utcnow
from app.services.actors import Actor
from app.services.quota import QuotaService
from app.tools.base import PDF, Tool, ToolContext
from app.tools.registry import ToolRegistry

log = logging.getLogger(__name__)

MAX_STEPS = 10


@dataclass(frozen=True)
class Upload:
    """An uploaded file already spooled to local disk by the API layer."""

    path: Path
    name: str
    size: int


@dataclass(frozen=True)
class Step:
    tool: Tool
    options: Any

    def as_json(self) -> dict:
        return {"tool": self.tool.id, "options": self.options.model_dump(mode="json")}


def safe_name(name: str) -> str:
    name = Path(name.replace("\\", "/")).name
    name = re.sub(r"[^\w.\- ()\[\]]+", "_", name, flags=re.UNICODE).strip(" .") or "file"
    return name[-150:]


class JobService:
    def __init__(
        self,
        *,
        db: Database,
        storage: FileStorage,
        queue: JobQueue,
        registry: ToolRegistry,
        quota: QuotaService,
        work_root: Path,
        file_ttl_hours: float,
        converter: DocumentConverter | None,
        ai: AIProvider | None,
        ghostscript: Ghostscript,
        ocr_languages: str,
        tool_timeout: int,
    ):
        self.db = db
        self.storage = storage
        self.queue = queue
        self.registry = registry
        self.quota = quota
        self.work_root = work_root
        self.file_ttl = timedelta(hours=file_ttl_hours)
        self.converter = converter
        self.ai = ai
        self.ghostscript = ghostscript
        self.ocr_languages = ocr_languages
        self.tool_timeout = tool_timeout

    # ---- validation -------------------------------------------------------------------------

    def parse_steps(self, raw_steps: list[dict]) -> list[Step]:
        if not raw_steps:
            raise ValidationFailed("Choose a tool.")
        if len(raw_steps) > MAX_STEPS:
            raise ValidationFailed(f"A workflow can have at most {MAX_STEPS} steps.")
        steps = []
        for index, raw in enumerate(raw_steps):
            tool = self.registry.get(str(raw.get("tool", "")))
            try:
                options = tool.Options.model_validate(raw.get("options") or {})
            except ValidationError as exc:
                first = exc.errors()[0]
                where = ".".join(str(p) for p in first["loc"]) or "options"
                raise ValidationFailed(f"{tool.name}: {where}: {first['msg']}") from None
            if index > 0:
                previous = steps[-1].tool
                if not previous.produces_pdf:
                    raise ValidationFailed(f"{previous.name} doesn't produce a PDF, so it must be the last step.")
                if ".pdf" not in tool.accepts:
                    raise ValidationFailed(f"{tool.name} can't take a PDF, so it must be the first step.")
            steps.append(Step(tool, options))
        return steps

    def _check_inputs(self, first: Tool, uploads: list[Upload]) -> None:
        if len(uploads) < first.min_files:
            raise ValidationFailed(f"{first.name} needs at least {first.min_files} file(s).")
        if first.max_files is not None and len(uploads) > first.max_files:
            raise ValidationFailed(f"{first.name} takes at most {first.max_files} file(s).")
        for upload in uploads:
            ext = Path(upload.name).suffix.lower()
            if ext not in first.accepts:
                raise ValidationFailed(f"'{upload.name}' isn't supported here. Use: {', '.join(first.accepts)}.")
            if ext in PDF and not _looks_like_pdf(upload.path):
                raise ValidationFailed(f"'{upload.name}' is not a valid PDF file.")

    # ---- lifecycle --------------------------------------------------------------------------

    def create(self, actor: Actor, raw_steps: list[dict], uploads: list[Upload]) -> Job:
        steps = self.parse_steps(raw_steps)
        self.quota.check_tools(actor, [s.tool for s in steps])
        self.quota.check_files(actor, [u.size for u in uploads])
        self._check_inputs(steps[0].tool, uploads)
        with self.db.session() as session:
            self.quota.check_rate(session, actor)
            now = utcnow()
            job = Job(
                user_id=actor.user.id if actor.user else None,
                guest_id=None if actor.user else actor.guest_id,
                ip_hash=actor.ip_hash,
                api_key_id=actor.api_key.id if actor.api_key else None,
                steps=[s.as_json() for s in steps],
                input_names=[safe_name(u.name) for u in uploads],
                input_bytes=sum(u.size for u in uploads),
                created_at=now,
                expires_at=now + self.file_ttl,
            )
            session.add(job)
            session.flush()
            for index, upload in enumerate(uploads):
                self.storage.put(self._input_key(job.id, index, job.input_names[index]), upload.path)
        self.queue.enqueue(job.id)
        return self.get(actor, job.id)

    def run(self, job_id: str) -> None:
        """Executed by the worker. Never raises: failures are recorded on the job."""
        with self.db.session() as session:
            job = session.get(Job, job_id)
            if job is None or job.status != "queued":
                return
            job.status, job.started_at = "running", utcnow()
            steps, names = list(job.steps), list(job.input_names)

        work = Path(tempfile.mkdtemp(prefix=f"job-{job_id}-", dir=self._ensure_work_root()))
        try:
            inputs = [
                self.storage.get(self._input_key(job_id, i, name), work / "in" / f"{i:03d}" / name)
                for i, name in enumerate(names)
            ]
            parsed = self.parse_steps(steps)
            for index, step in enumerate(parsed):
                ctx = ToolContext(
                    work_dir=work / f"step-{index}",
                    converter=self.converter,
                    ai=self.ai,
                    ghostscript=self.ghostscript,
                    ocr_languages=self.ocr_languages,
                    timeout_seconds=self.tool_timeout,
                )
                ctx.work_dir.mkdir(parents=True)
                inputs = step.tool.run(inputs, step.options, ctx)
            result = self._package(inputs, work, names, parsed)
            self.storage.put(self._output_key(job_id, result.name), result)
            with self.db.session() as session:
                job = session.get(Job, job_id)
                job.status, job.finished_at = "succeeded", utcnow()
                job.output_name, job.output_bytes, job.output_count = result.name, result.stat().st_size, len(inputs)
        except FolioError as exc:
            self._fail(job_id, exc.message, exc.code)
        except Exception:
            log.exception("Job %s crashed", job_id)
            self._fail(job_id, "Something went wrong while processing your file.", "internal_error")
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _fail(self, job_id: str, message: str, code: str) -> None:
        with self.db.session() as session:
            job = session.get(Job, job_id)
            job.status, job.error, job.error_code, job.finished_at = "failed", message, code, utcnow()

    @staticmethod
    def _package(outputs: list[Path], work: Path, names: list[str], steps: list[Step]) -> Path:
        if len(outputs) == 1:
            return outputs[0]
        base = Path(names[0]).stem if names else steps[-1].tool.id
        archive = work / f"{base}-{steps[-1].tool.id}.zip"
        used: set[str] = set()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in outputs:
                arcname, n = path.name, 1
                while arcname in used:
                    arcname = f"{path.stem}-{n}{path.suffix}"
                    n += 1
                used.add(arcname)
                zf.write(path, arcname)
        return archive

    # ---- queries ----------------------------------------------------------------------------

    def get(self, actor: Actor, job_id: str) -> Job:
        with self.db.session() as session:
            job = session.get(Job, job_id)
            if job is None:
                raise NotFound("Task not found.")
            self._authorize(actor, job)
            return job

    def history(self, actor: Actor, limit: int = 50) -> list[Job]:
        if actor.user is None:
            return []
        with self.db.session() as session:
            return list(
                session.scalars(
                    select(Job).where(Job.user_id == actor.user.id).order_by(Job.created_at.desc()).limit(limit)
                )
            )

    def open_output(self, actor: Actor, job_id: str):
        job = self.get(actor, job_id)
        if job.status != "succeeded" or job.files_deleted or as_utc(job.expires_at) < utcnow():
            raise NotFound("This file is no longer available. Files are deleted automatically for your privacy.")
        return job, self.storage.open_stream(self._output_key(job.id, job.output_name))

    def delete_files(self, actor: Actor, job_id: str) -> None:
        job = self.get(actor, job_id)
        self.storage.delete_prefix(f"jobs/{job.id}/")
        with self.db.session() as session:
            session.get(Job, job.id).files_deleted = True

    @staticmethod
    def _authorize(actor: Actor, job: Job) -> None:
        if job.user_id is not None:
            if actor.user is None or actor.user.id != job.user_id:
                raise NotFound("Task not found.")
        elif not actor.guest_id or actor.guest_id != job.guest_id:
            raise Forbidden("This task belongs to another session.")

    # ---- helpers ----------------------------------------------------------------------------

    @staticmethod
    def _input_key(job_id: str, index: int, name: str) -> str:
        return f"jobs/{job_id}/in/{index:03d}-{name}"

    @staticmethod
    def _output_key(job_id: str, name: str) -> str:
        return f"jobs/{job_id}/out/{name}"

    def _ensure_work_root(self) -> Path:
        self.work_root.mkdir(parents=True, exist_ok=True)
        return self.work_root


def _looks_like_pdf(path: Path) -> bool:
    with path.open("rb") as fh:
        return b"%PDF" in fh.read(1024)
