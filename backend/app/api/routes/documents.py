"""My documents (files kept on purpose) and share links, including the public side of a link."""

import tempfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field

from app.api.deps import SpooledUploads, client_ip_hash, container, spooler, user
from app.container import Container
from app.services.actors import Actor

router = APIRouter(tags=["documents"])


def _file_response(meta: dict, stream, *, download: bool) -> StreamingResponse:
    disposition = "attachment" if download else "inline"
    return StreamingResponse(
        stream,
        media_type=meta["content_type"],
        headers={
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(meta['name'])}",
            "Content-Length": str(meta["size"]),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/documents", summary="Your saved documents and storage use")
def list_documents(a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    return {"documents": c.documents.all(a), "usage": c.documents.usage(a)}


@router.post("/documents", status_code=201, summary="Save a file to your documents")
async def upload(
    files: list[UploadFile] = File(...),
    a: Actor = Depends(user),
    spool: SpooledUploads = Depends(spooler),
    c: Container = Depends(container),
) -> dict:
    uploads = await spool.add(files[:50])
    return {"documents": [c.documents.add(a, u.path, u.name) for u in uploads]}


@router.post("/documents/from-job/{job_id}", status_code=201, summary="Keep a task's result")
def from_job(job_id: str, a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    with tempfile.TemporaryDirectory(prefix="keep-") as tmp:
        return c.documents.add_from_job(a, job_id, Path(tmp))


@router.get("/documents/{doc_id}/file", summary="Open or download a document")
def open_document(doc_id: str, download: bool = False, a: Actor = Depends(user), c: Container = Depends(container)):
    meta, stream = c.documents.open(a, doc_id)
    return _file_response(meta, stream, download=download)


class RenameIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=250)


@router.patch("/documents/{doc_id}", summary="Rename a document")
def rename(doc_id: str, body: RenameIn, a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    return c.documents.rename(a, doc_id, body.name)


@router.delete("/documents/{doc_id}", status_code=204, summary="Delete a document and its share links")
def delete(doc_id: str, a: Actor = Depends(user), c: Container = Depends(container)) -> None:
    c.documents.delete(a, doc_id)


class ShareIn(BaseModel):
    expires_in_days: int | None = Field(None, ge=1, le=365)
    password: str | None = Field(None, min_length=4, max_length=128)
    max_downloads: int | None = Field(None, ge=1, le=100000)
    allow_download: bool = True


@router.get("/documents/{doc_id}/shares", summary="Active share links")
def shares(doc_id: str, a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    return {"shares": c.documents.shares(a, doc_id)}


@router.post("/documents/{doc_id}/shares", status_code=201, summary="Create a share link")
def share(doc_id: str, body: ShareIn, a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    return c.documents.share(a, doc_id, **body.model_dump())


@router.delete("/documents/{doc_id}/shares/{share_id}", status_code=204, summary="Turn a share link off")
def revoke(doc_id: str, share_id: str, a: Actor = Depends(user), c: Container = Depends(container)) -> None:
    c.documents.revoke(a, doc_id, share_id)


class SendIn(BaseModel):
    email: EmailStr
    message: str | None = Field(None, max_length=2000)
    expires_in_days: int = Field(7, ge=1, le=30)


@router.post("/documents/{doc_id}/send", status_code=201, summary="Email someone a link to a document")
def send(doc_id: str, body: SendIn, a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    c.limiter.hit(f"send:{a.user.id}", limit=30, window_seconds=3600)
    return c.documents.send(
        a, doc_id, email=str(body.email), message=body.message, expires_in_days=body.expires_in_days
    )


# ---- public: whoever holds the link ------------------------------------------------------------------------------


@router.get("/s/{token}", summary="What a share link points to")
def shared(token: str, request: Request, c: Container = Depends(container)) -> dict:
    c.limiter.hit(f"share:{client_ip_hash(request, c)}", limit=300, window_seconds=600)
    return c.documents.shared(token)


class UnlockIn(BaseModel):
    password: str = Field("", max_length=128)


@router.post("/s/{token}/unlock", summary="Enter a share link's password")
def unlock(token: str, body: UnlockIn, request: Request, c: Container = Depends(container)) -> dict:
    c.limiter.hit(f"share-pw:{token}:{client_ip_hash(request, c)}", limit=10, window_seconds=600)
    return {"grant": c.documents.unlock(token, body.password)}


@router.get("/s/{token}/file", summary="The shared file")
def shared_file(token: str, grant: str, request: Request, download: bool = False, c: Container = Depends(container)):
    c.limiter.hit(f"share:{client_ip_hash(request, c)}", limit=300, window_seconds=600)
    meta, stream = c.documents.shared_file(token, grant, download=download)
    return _file_response(meta, stream, download=download)
