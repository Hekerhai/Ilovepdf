"""Request signatures from other people. Owner endpoints need an account; signer endpoints use the emailed link."""

import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from app.api.deps import SpooledUploads, client_ip, client_ip_hash, container, spooler, user
from app.container import Container
from app.domain.errors import ValidationFailed
from app.services.actors import Actor
from app.services.esign import RequestIn, SignIn

router = APIRouter(tags=["esign"])


def _pdf_response(name: str, stream) -> StreamingResponse:
    return StreamingResponse(
        stream,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(name)}",
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/esign/requests", status_code=201, summary="Send a PDF out for signature")
async def create_request(
    request: Request,
    file: UploadFile = File(...),
    details: str = Form(..., description="JSON: title, message, signers, fields, sequential, expires_in_days"),
    a: Actor = Depends(user),
    spool: SpooledUploads = Depends(spooler),
    c: Container = Depends(container),
) -> dict:
    c.limiter.hit(f"esign:create:{a.user.id}", limit=30, window_seconds=3600)
    try:
        body = RequestIn.model_validate(json.loads(details))
    except (ValueError, ValidationError) as exc:
        message = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else "'details' must be valid JSON."
        raise ValidationFailed(message.removeprefix("Value error, ")) from None
    if not (file.filename or "").lower().endswith(".pdf"):
        raise ValidationFailed("Upload a PDF to send for signature.")
    [upload] = await spool.add([file])
    return c.esign.create(a, upload.path, upload.name, body, ip=client_ip(request))


@router.get("/esign/requests", summary="Your signature requests")
def list_requests(a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    return {"requests": c.esign.list_for(a.user)}


@router.get("/esign/requests/{request_id}", summary="One request, with its history")
def get_request(request_id: str, a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    return c.esign.detail(a.user, request_id)


@router.get("/esign/requests/{request_id}/document", summary="The original, or the signed copy once complete")
def owner_document(request_id: str, a: Actor = Depends(user), c: Container = Depends(container)):
    return _pdf_response(*c.esign.owner_document(a.user, request_id))


@router.post("/esign/requests/{request_id}/remind", summary="Email everyone who hasn't signed yet")
def remind(request_id: str, a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    c.limiter.hit(f"esign:remind:{request_id}", limit=3, window_seconds=86400)
    return c.esign.remind(a.user, request_id)


@router.post("/esign/requests/{request_id}/cancel", summary="Withdraw a request")
def cancel(request_id: str, a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    return c.esign.cancel(a.user, request_id)


@router.delete("/esign/requests/{request_id}", status_code=204, summary="Delete a request and its documents")
def delete(request_id: str, a: Actor = Depends(user), c: Container = Depends(container)) -> None:
    c.esign.delete(a.user, request_id)


# ---- signer side: the link in the email is the only credential --------------------------------------------------


def _limit(request: Request, c: Container) -> None:
    c.limiter.hit(f"esign:sign:{client_ip_hash(request, c)}", limit=120, window_seconds=600)


@router.get("/esign/sign/{token}", summary="What a signer sees")
def signer_view(token: str, request: Request, c: Container = Depends(container)) -> dict:
    _limit(request, c)
    return c.esign.view(token, ip=client_ip(request), user_agent=request.headers.get("user-agent"))


@router.get("/esign/sign/{token}/document", summary="The document to sign")
def signer_document(token: str, request: Request, c: Container = Depends(container)):
    _limit(request, c)
    return _pdf_response(*c.esign.signer_document(token))


@router.post("/esign/sign/{token}", summary="Sign")
def sign(token: str, body: SignIn, request: Request, c: Container = Depends(container)) -> dict:
    _limit(request, c)
    return c.esign.sign(token, body, ip=client_ip(request), user_agent=request.headers.get("user-agent"))


class DeclineIn(BaseModel):
    reason: str | None = Field(None, max_length=1000)


@router.post("/esign/sign/{token}/decline", summary="Decline to sign")
def decline(token: str, body: DeclineIn, request: Request, c: Container = Depends(container)) -> dict:
    _limit(request, c)
    return c.esign.decline(token, body.reason, ip=client_ip(request), user_agent=request.headers.get("user-agent"))
