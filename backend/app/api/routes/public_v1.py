"""Public developer API (/v1). Same engine as the web app, authenticated with API keys only."""

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import SpooledUploads, api_user, container, spooler
from app.api.routes import jobs as web
from app.api.routes.tools import list_tools
from app.api.schemas import job_out
from app.container import Container
from app.infra.webhooks import SIGNATURE_HEADER
from app.services.actors import Actor

router = APIRouter(tags=["developer API v1"])


@router.get("/tools", summary="List tools and their option schemas")
def tools(_: Actor = Depends(api_user), c: Container = Depends(container)) -> dict:
    return list_tools(c)


@router.post("/jobs", status_code=202, summary="Create a task (1 credit)")
async def create_job(
    files: list[UploadFile] = File(default=[]),
    tool: str | None = Form(None),
    options: str | None = Form(None),
    steps: str | None = Form(None),
    webhook_url: str | None = Form(None, description="Called with a signed POST when the task finishes"),
    a: Actor = Depends(api_user),
    spool: SpooledUploads = Depends(spooler),
    c: Container = Depends(container),
) -> dict:
    raw_steps = web.parse_steps_form(tool, options, steps)
    uploads = await spool.add(files)
    return job_out(c.jobs.create(a, raw_steps, uploads, webhook_url=webhook_url), prefix="/v1")


@router.get("/jobs/{job_id}", summary="Task status")
def get_job(job_id: str, a: Actor = Depends(api_user), c: Container = Depends(container)) -> dict:
    return job_out(c.jobs.get(a, job_id), prefix="/v1")


@router.get("/jobs/{job_id}/download", summary="Download the result")
def download(job_id: str, a: Actor = Depends(api_user), c: Container = Depends(container)):
    return web.download(job_id, a, c)


@router.delete("/jobs/{job_id}", status_code=204, summary="Delete a task's files now")
def delete(job_id: str, a: Actor = Depends(api_user), c: Container = Depends(container)) -> None:
    c.jobs.delete_files(a, job_id)


@router.get("/usage", summary="This month's credit usage")
def usage(a: Actor = Depends(api_user), c: Container = Depends(container)) -> dict:
    with c.db.session() as session:
        return c.quota.api_usage(session, a)


@router.post("/forms/fields", summary="List a PDF form's fields (free, no credit)")
async def form_fields(
    file: UploadFile = File(...),
    a: Actor = Depends(api_user),
    spool: SpooledUploads = Depends(spooler),
    c: Container = Depends(container),
) -> dict:
    c.limiter.hit(f"v1:fields:{a.user.id}", limit=120, window_seconds=60)
    [upload] = await spool.add([file])
    return {"fields": c.jobs.describe_form(upload)}


@router.get("/webhooks/secret", summary="The secret that signs your webhooks")
def webhook_secret(a: Actor = Depends(api_user), c: Container = Depends(container)) -> dict:
    return {"secret": c.auth.webhook_secret(a.user.id), "header": SIGNATURE_HEADER}
