import httpx
import pytest

from app.domain.errors import ValidationFailed
from app.infra.url_import import UrlImporter, check_public, direct_link


def test_direct_links():
    assert direct_link("https://drive.google.com/file/d/abc_123/view?usp=sharing") == (
        "https://drive.google.com/uc?export=download&id=abc_123"
    )
    assert direct_link("https://docs.google.com/document/d/XYZ/edit") == (
        "https://docs.google.com/document/d/XYZ/export?format=pdf"
    )
    assert direct_link("https://www.dropbox.com/s/k/report.pdf?dl=0") == "https://www.dropbox.com/s/k/report.pdf?dl=1"
    assert direct_link("example.com/a.pdf") == "https://example.com/a.pdf"


def test_private_addresses_are_refused():
    for url in ("http://127.0.0.1/x.pdf", "http://169.254.169.254/latest/meta-data", "ftp://example.com/a"):
        with pytest.raises(ValidationFailed):
            check_public(url)


def _importer(handler, blocked=()):
    def check(url):
        if any(b in url for b in blocked):
            raise ValidationFailed("That link points to a private address, so it can't be imported.")

    return UrlImporter(transport=httpx.MockTransport(handler), check=check)


def test_fetch_follows_redirects_and_names_the_file(tmp_path):
    def handler(request):
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/files/9"})
        return httpx.Response(
            200,
            content=b"%PDF-1.4 hello",
            headers={"content-type": "application/pdf", "content-disposition": 'attachment; filename="Q3 report.pdf"'},
        )

    path, name, kind = _importer(handler).fetch("https://files.example/start", max_bytes=1000, work_dir=tmp_path)
    assert name == "Q3 report.pdf" and kind == "application/pdf" and path.read_bytes() == b"%PDF-1.4 hello"


def test_fetch_rechecks_redirects_and_limits_size(tmp_path):
    def to_internal(request):
        if request.url.host == "files.example":
            return httpx.Response(301, headers={"location": "http://internal.local/secret"})
        return httpx.Response(200, content=b"secret")

    with pytest.raises(ValidationFailed, match="private"):
        _importer(to_internal, blocked=("internal.local",)).fetch(
            "https://files.example/a", max_bytes=1000, work_dir=tmp_path
        )

    def big(request):
        return httpx.Response(200, content=b"x" * 5000, headers={"content-type": "image/png"})

    with pytest.raises(ValidationFailed, match="bigger"):
        _importer(big).fetch("https://files.example/img", max_bytes=1000, work_dir=tmp_path)

    def page(request):
        return httpx.Response(200, content=b"<html></html>", headers={"content-type": "text/html; charset=utf-8"})

    with pytest.raises(ValidationFailed, match="web page"):
        _importer(page).fetch("https://files.example/", max_bytes=1000, work_dir=tmp_path)


def test_import_endpoint(app_env, tmp_path):
    c, client = app_env

    def handler(request):
        return httpx.Response(200, content=b"PNGDATA", headers={"content-type": "image/png"})

    c.importer = _importer(handler)
    r = client.post("/api/import/url", json={"url": "https://img.example/photos/cat"})
    assert r.status_code == 200 and r.content == b"PNGDATA"
    assert r.headers["x-file-name"] == "cat.png" and r.headers["content-type"] == "image/png"
    c.importer = UrlImporter()
    bad = client.post("/api/import/url", json={"url": "http://127.0.0.1:8000/api/health"})
    assert bad.status_code == 422
