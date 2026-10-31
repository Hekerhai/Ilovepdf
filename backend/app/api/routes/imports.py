"""Bring a file in from a link (a public URL, or a Google Drive, Dropbox or OneDrive share link)."""

import shutil
import tempfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from app.api.deps import actor, client_ip_hash, container
from app.container import Container
from app.services.actors import Actor

router = APIRouter(tags=["import"])


class ImportIn(BaseModel):
    url: str = Field(..., min_length=4, max_length=4000)


@router.post("/import/url", summary="Fetch a file from a link, to use in a tool")
def import_url(body: ImportIn, request: Request, a: Actor = Depends(actor), c: Container = Depends(container)):
    who = a.user.id if a.user else client_ip_hash(request, c)
    c.limiter.hit(f"import:{who}", limit=30, window_seconds=600)
    work = Path(tempfile.mkdtemp(prefix="import-", dir=c.settings.work_dir if c.settings.work_dir.exists() else None))
    try:
        path, name, kind = c.importer.fetch(body.url, max_bytes=a.plan.max_file_bytes, work_dir=work)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    return FileResponse(
        path,
        media_type=kind,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}",
            "X-File-Name": quote(name),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
        background=BackgroundTask(shutil.rmtree, work, ignore_errors=True),
    )
