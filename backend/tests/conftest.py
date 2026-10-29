import base64
import io
import os
import tempfile
from pathlib import Path

import pytest
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

_TMP = tempfile.mkdtemp(prefix="folio-test-")
os.environ.update(
    ENVIRONMENT="test",
    QUEUE_MODE="inline",
    DATABASE_URL=f"sqlite:///{_TMP}/default.db",
    STORAGE_DIR=f"{_TMP}/files",
    WORK_DIR=f"{_TMP}/work",
)


def make_pdf(path: Path, pages: int = 3, text: str = "Hello page", size=A4) -> Path:
    c = Canvas(str(path), pagesize=size)
    for i in range(1, pages + 1):
        c.setFont("Helvetica-Bold", 24)
        c.drawString(72, size[1] - 96, f"Heading {i}")
        c.setFont("Helvetica", 12)
        c.drawString(72, size[1] - 140, f"{text} {i}")
        c.drawString(72, size[1] - 160, "Name    Qty    Price")
        c.showPage()
    c.save()
    return path


def make_image(path: Path, size=(400, 300), color=(200, 30, 30), mode="RGB") -> Path:
    Image.new(mode, size, color if mode == "RGB" else color + (128,)).save(path)
    return path


def data_url_png(size=(200, 80)) -> str:
    buf = io.BytesIO()
    Image.new("RGBA", size, (0, 0, 0, 0)).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@pytest.fixture
def pdf3(tmp_path) -> Path:
    return make_pdf(tmp_path / "doc.pdf", 3)


@pytest.fixture
def pdf2(tmp_path) -> Path:
    return make_pdf(tmp_path / "other.pdf", 2, text="Other text")


@pytest.fixture
def app_env(tmp_path):
    """A fresh container (SQLite, local storage, inline queue) wired into the FastAPI app."""
    from fastapi.testclient import TestClient

    from app.api.deps import container as container_dep
    from app.config import Settings
    from app.container import build_container
    from app.main import app

    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/test.db",
        queue_mode="inline",
        storage_dir=tmp_path / "files",
        work_dir=tmp_path / "work",
        secret_key="test-secret-0123456789abcdef0123456789",
        razorpay_key_id="rzp_test",
        razorpay_key_secret="secret",
        razorpay_webhook_secret="whsec",
    )
    c = build_container(settings)
    app.dependency_overrides[container_dep] = lambda: c
    try:
        yield c, TestClient(app)
    finally:
        app.dependency_overrides.clear()
