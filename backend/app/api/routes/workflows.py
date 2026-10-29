from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field

from app.api.deps import SpooledUploads, actor, container, spooler, user
from app.api.schemas import job_out, workflow_out
from app.container import Container
from app.services.actors import Actor

router = APIRouter(prefix="/workflows", tags=["workflows"])


class StepIn(BaseModel):
    tool: str
    options: dict = Field(default_factory=dict)


class WorkflowIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    steps: list[StepIn] = Field(..., min_length=1, max_length=10)
    team_id: str | None = None


@router.get("")
def list_workflows(a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    return {"workflows": [workflow_out(w) for w in c.workflows.list(a)]}


@router.post("", status_code=201)
def create_workflow(body: WorkflowIn, a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    steps = [s.model_dump() for s in body.steps]
    return workflow_out(c.workflows.save(a, body.name, steps, body.team_id))


@router.put("/{workflow_id}")
def update_workflow(workflow_id: str, body: WorkflowIn, a: Actor = Depends(user), c: Container = Depends(container)):
    steps = [s.model_dump() for s in body.steps]
    return workflow_out(c.workflows.save(a, body.name, steps, body.team_id, workflow_id=workflow_id))


@router.delete("/{workflow_id}", status_code=204)
def delete_workflow(workflow_id: str, a: Actor = Depends(user), c: Container = Depends(container)) -> None:
    c.workflows.delete(a, workflow_id)


@router.post("/{workflow_id}/run", status_code=202, summary="Run a saved workflow on uploaded files")
async def run_workflow(
    workflow_id: str,
    files: list[UploadFile] = File(...),
    a: Actor = Depends(actor),
    spool: SpooledUploads = Depends(spooler),
    c: Container = Depends(container),
) -> dict:
    wf = c.workflows.get(a, workflow_id)
    uploads = await spool.add(files)
    return job_out(c.jobs.create(a, wf.steps, uploads))
