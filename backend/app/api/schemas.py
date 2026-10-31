"""Response shapes shared by routes."""

from app.infra.db import Job, User, Workflow, as_utc
from app.plans import Plan


def job_out(job: Job, prefix: str = "/api") -> dict:
    expires = as_utc(job.expires_at)
    return {
        "id": job.id,
        "status": job.status,
        "steps": job.steps,
        "inputs": job.input_names,
        "input_bytes": job.input_bytes,
        "output_name": job.output_name,
        "output_bytes": job.output_bytes,
        "output_count": job.output_count,
        "error": job.error,
        "error_code": job.error_code,
        "created_at": as_utc(job.created_at).isoformat(),
        "finished_at": as_utc(job.finished_at).isoformat() if job.finished_at else None,
        "expires_at": expires.isoformat(),
        "files_deleted": job.files_deleted,
        "webhook_status": job.webhook_status,
        "download_url": f"{prefix}/jobs/{job.id}/download"
        if job.status == "succeeded" and not job.files_deleted
        else None,
    }


def plan_out(plan: Plan) -> dict:
    return {
        "id": plan.id.value,
        "name": plan.name,
        "max_file_mb": plan.max_file_bytes // (1024 * 1024),
        "max_files_per_task": plan.max_files_per_task,
        "tasks_per_day": plan.tasks_per_day,
        "premium_tools": plan.premium_tools,
        "workflows": plan.max_workflows != 0,
        "team_workspace": plan.team_workspace,
        "esign_requests_per_month": plan.esign_requests_per_month,
        "storage_mb": plan.storage_bytes // (1024 * 1024),
    }


def user_out(user: User, plan: Plan) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "email_verified": user.email_verified,
        "has_password": bool(user.password_hash),
        "google_linked": bool(user.google_sub),
        "plan": plan_out(plan),
    }


def workflow_out(wf: Workflow) -> dict:
    return {
        "id": wf.id,
        "name": wf.name,
        "steps": wf.steps,
        "team_id": wf.team_id,
        "owner_id": wf.user_id,
        "updated_at": as_utc(wf.updated_at).isoformat(),
    }
