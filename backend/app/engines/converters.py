"""DocumentConverter adapters: Gotenberg (preferred in Docker) and a local LibreOffice fallback."""

import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx

from app.domain.errors import ToolFailed, ValidationFailed
from app.engines.process import run


class GotenbergConverter:
    """Talks to a Gotenberg container (LibreOffice + Chromium behind an HTTP API)."""

    def __init__(self, base_url: str, timeout: int = 600):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def office_to_pdf(self, source: Path, output: Path) -> Path:
        with source.open("rb") as fh:
            return self._post("/forms/libreoffice/convert", {"files": (source.name, fh)}, {}, output)

    def html_to_pdf(self, *, output: Path, html_file: Path | None = None, url: str | None = None) -> Path:
        data = {"printBackground": "true", "marginTop": "0.4", "marginBottom": "0.4"}
        if url:
            return self._post("/forms/chromium/convert/url", {}, {**data, "url": url}, output)
        if html_file is None:
            raise ValidationFailed("Provide an HTML file or a URL.")
        with html_file.open("rb") as fh:
            return self._post("/forms/chromium/convert/html", {"files": ("index.html", fh)}, data, output)

    def _post(self, path: str, files: dict, data: dict, output: Path) -> Path:
        try:
            response = httpx.post(self.base_url + path, files=files, data=data, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise ToolFailed(f"The conversion service is unreachable ({exc.__class__.__name__}).") from None
        if response.status_code != 200:
            raise ToolFailed(f"Conversion failed: {response.text[:200]}")
        output.write_bytes(response.content)
        return output


class LibreOfficeConverter:
    """Runs ``soffice --headless`` directly. Used when no Gotenberg service is configured."""

    def __init__(self, binary: str = "soffice", timeout: int = 600):
        self.binary = binary
        self.timeout = timeout

    def office_to_pdf(self, source: Path, output: Path) -> Path:
        return self._convert(source, output, "pdf")

    def html_to_pdf(self, *, output: Path, html_file: Path | None = None, url: str | None = None) -> Path:
        if url:
            raise ToolFailed("URL to PDF needs the Gotenberg service (set GOTENBERG_URL).")
        if html_file is None:
            raise ValidationFailed("Provide an HTML file or a URL.")
        return self._convert(html_file, output, "pdf:writer_web_pdf_Export")

    def convert(self, source: Path, output: Path, target: str) -> Path:
        """Generic LibreOffice conversion, e.g. target='docx'."""
        return self._convert(source, output, target)

    def _convert(self, source: Path, output: Path, target: str) -> Path:
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "profile"
            cmd = [
                self.binary,
                f"-env:UserInstallation=file://{profile}",
                "--headless",
                "--norestore",
                "--convert-to",
                target,
                "--outdir",
                tmp,
                str(source),
            ]
            try:
                run(cmd, timeout=self.timeout, error=f"Could not convert '{source.name}'.")
            except subprocess.SubprocessError:
                raise ToolFailed(f"Could not convert '{source.name}'.") from None
            ext = target.split(":")[0]
            produced = Path(tmp) / f"{source.stem}.{ext}"
            if not produced.exists():
                raise ToolFailed(f"Could not convert '{source.name}'. Is it a valid document?")
            shutil.move(produced, output)
        return output
