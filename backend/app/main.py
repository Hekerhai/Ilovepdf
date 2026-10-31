"""FastAPI application factory."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import account, auth, billing, esign, jobs, public_v1, teams, tools, workflows
from app.config import get_settings
from app.container import get_container
from app.domain.errors import FolioError

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.environment == "production" and (
        settings.secret_key == "change-me-in-production" or len(settings.secret_key) < 32
    ):
        raise RuntimeError("Set SECRET_KEY to a random string of at least 32 characters.")
    get_container()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        lifespan=lifespan,
        title=f"{settings.brand_name} API",
        version="1.0.0",
        description=(
            "Every PDF tool as an API. Authenticate with `Authorization: Bearer fk_live_...`. "
            "Create a task with `POST /v1/jobs`, poll `GET /v1/jobs/{id}` until `status` is `succeeded`, "
            "then download from `download_url`. Files are deleted automatically."
        ),
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    @app.exception_handler(FolioError)
    async def folio_error(_: Request, exc: FolioError):
        return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {"msg": "Invalid request", "loc": []}
        where = ".".join(str(p) for p in first["loc"] if p not in ("body", "query"))
        message = f"{where}: {first['msg']}" if where else first["msg"]
        return JSONResponse({"error": {"code": "invalid_input", "message": message}}, status_code=422)

    for module in (tools, jobs, auth, account, teams, workflows, billing, esign):
        app.include_router(module.router, prefix="/api")
    app.include_router(public_v1.router, prefix="/v1")

    @app.get("/api/health", include_in_schema=False)
    def health() -> dict:
        with get_container().db.engine.connect():
            pass
        return {"status": "ok"}

    return app


app = create_app()
