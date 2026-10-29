import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse

from app.api.deps import SpooledUploads, actor, container, spooler, user
from app.api.schemas import job_out
from app.container import Container
from app.domain.errors import ValidationFailed
from app.services.actors import Actor

router = APIRouter(tags=["jobs"])

MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".zip": "application/zip",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".html": "text/html; charset=utf-8",
}


def parse_steps_form(tool: str | None, options: str | None, steps: str | None) -> list[dict]:
    try:
        if steps:
            parsed = json.loads(steps)
            if not isinstance(parsed, list):
                raise ValueError
            return parsed
        if not tool:
            raise ValidationFailed("Send 'tool' (with optional 'options') or 'steps'.")
        return [{"tool": tool, "options": json.loads(options) if options else {}}]
    except (ValueError, TypeError):
        raise ValidationFailed("'options' and 'steps' must be valid JSON.") from None


@router.post("/jobs", status_code=202, summary="Start a task: one tool or a chain of tools")
async def create_job(
    files: list[UploadFile] = File(default=[]),
    tool: str | None = Form(None, description="Tool id, e.g. 'compress'"),
    options: str | None = Form(None, description="JSON object of tool options"),
    steps: str | None = Form(None, description='JSON list for workflows: [{"tool": "...", "options": {...}}]'),
    a: Actor = Depends(actor),
    spool: SpooledUploads = Depends(spooler),
    c: Container = Depends(container),
) -> dict:
    c.limiter.hit(f"jobs:{a.user.id if a.user else a.ip_hash}", limit=60, window_seconds=60)
    raw_steps = parse_steps_form(tool, options, steps)
    uploads = await spool.add(files)
    return job_out(c.jobs.create(a, raw_steps, uploads))


@router.get("/jobs", summary="Your recent tasks")
def list_jobs(a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    return {"jobs": [job_out(j) for j in c.jobs.history(a)]}


@router.get("/jobs/{job_id}", summary="Task status")
def get_job(job_id: str, a: Actor = Depends(actor), c: Container = Depends(container)) -> dict:
    return job_out(c.jobs.get(a, job_id))


@router.get("/jobs/{job_id}/download", summary="Download the result")
def download(job_id: str, a: Actor = Depends(actor), c: Container = Depends(container)):
    job, stream = c.jobs.open_output(a, job_id)
    name = job.output_name
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return StreamingResponse(
        stream,
        media_type=MEDIA_TYPES.get(ext, "application/octet-stream"),
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}",
            "Content-Length": str(job.output_bytes),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/jobs/{job_id}", status_code=204, summary="Delete a task's files now")
def delete_job(job_id: str, a: Actor = Depends(actor), c: Container = Depends(container)) -> None:
    c.jobs.delete_files(a, job_id)
