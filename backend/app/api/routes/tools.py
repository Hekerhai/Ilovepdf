from fastapi import APIRouter, Depends

from app.api.deps import container
from app.container import Container
from app.tools.base import CATEGORY_LABELS

router = APIRouter(tags=["tools"])


@router.get("/tools", summary="List every tool with its options schema")
def list_tools(c: Container = Depends(container)) -> dict:
    return {
        "categories": [{"id": k.value, "name": v} for k, v in CATEGORY_LABELS.items()],
        "tools": [tool.describe() for tool in c.registry.all()],
    }


@router.get("/config", summary="Public runtime configuration for the web app")
def public_config(c: Container = Depends(container)) -> dict:
    s = c.settings
    return {
        "brand_name": s.brand_name,
        "file_ttl_hours": s.file_ttl_hours,
        "google_sign_in": c.auth.google_enabled,
        "ai_available": c.ai.available,
        "payments": {name: g.configured for name, g in c.billing.gateways.items()},
        "pickers": {
            "dropbox_app_key": s.dropbox_app_key,
            "google": (
                {"client_id": s.google_client_id, "api_key": s.google_picker_api_key, "app_id": s.google_app_id}
                if s.google_client_id and s.google_picker_api_key
                else None
            ),
        },
    }
