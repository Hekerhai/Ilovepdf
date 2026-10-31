"""Fetch a file from a public link so it can go into any tool, as if the user had uploaded it.

Every hop of a redirect is checked against private and internal addresses (SSRF), the size is capped while
streaming, and share pages of common storage services are turned into their direct-download links.
"""

import ipaddress
import mimetypes
import re
import socket
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit, urlunsplit

import httpx

from app.domain.errors import ValidationFailed
from app.services.jobs import safe_name

MAX_REDIRECTS = 5
USER_AGENT = "FolioImporter/1.0 (+https://github.com/folio-pdf)"


def check_public(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValidationFailed("Enter an http(s) link.")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    except OSError:
        raise ValidationFailed(f"Couldn't find the server '{parts.hostname}'.") from None
    if any(not ipaddress.ip_address(info[4][0]).is_global for info in infos):
        raise ValidationFailed("That link points to a private address, so it can't be imported.")


def direct_link(url: str) -> str:
    """Share pages of Google Drive, Dropbox and OneDrive become their direct-download URLs."""
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host == "drive.google.com":
        m = re.match(r"/file/d/([\w-]+)", parts.path)
        file_id = m.group(1) if m else dict(parse_qsl(parts.query)).get("id")
        if file_id:
            return f"https://drive.google.com/uc?export=download&id={file_id}"
    if host == "docs.google.com":
        m = re.match(r"/(document|spreadsheets|presentation)/d/([\w-]+)", parts.path)
        if m:
            return f"https://docs.google.com/{m.group(1)}/d/{m.group(2)}/export?format=pdf"
    if host in ("www.dropbox.com", "dropbox.com"):
        query = dict(parse_qsl(parts.query))
        query.pop("dl", None)
        query["dl"] = "1"
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
    if host in ("1drv.ms", "onedrive.live.com") and "download" not in parts.query:
        sep = "&" if parts.query else ""
        return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query + sep + "download=1", ""))
    return url


def _file_name(response: httpx.Response, url: str) -> str:
    disposition = response.headers.get("content-disposition", "")
    m = re.search(r"filename\*\s*=\s*[\w-]+''([^;]+)", disposition) or re.search(
        r'filename\s*=\s*"?([^";]+)"?', disposition
    )
    name = unquote(m.group(1)).strip() if m else unquote(Path(urlsplit(url).path).name)
    name = safe_name(name or "download")
    if not Path(name).suffix:
        kind = response.headers.get("content-type", "").split(";")[0].strip()
        name += mimetypes.guess_extension(kind) or ""
    return name


class UrlImporter:
    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        check: Callable[[str], None] = check_public,
        timeout: float = 30,
    ):
        self.transport = transport
        self.check = check
        self.timeout = timeout

    def fetch(self, url: str, *, max_bytes: int, work_dir: Path) -> tuple[Path, str, str]:
        """Download to work_dir. Returns (path, file name, content type)."""
        if len(url) > 4000:
            raise ValidationFailed("That link is too long.")
        url = direct_link(url)
        with httpx.Client(
            transport=self.transport, timeout=self.timeout, follow_redirects=False, headers={"User-Agent": USER_AGENT}
        ) as client:
            for _ in range(MAX_REDIRECTS + 1):
                self.check(url)  # every hop: a public URL may redirect to an internal one
                with client.stream("GET", url) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers.get("location", ""))
                        continue
                    if response.status_code >= 400:
                        raise ValidationFailed(f"The link answered with an error ({response.status_code}).")
                    kind = response.headers.get("content-type", "").split(";")[0].strip().lower()
                    if kind == "text/html":
                        raise ValidationFailed(
                            "That link opens a web page, not a file. Use a direct download link, or "
                            "HTML to PDF to convert the page."
                        )
                    length = int(response.headers.get("content-length") or 0)
                    if length > max_bytes:
                        raise ValidationFailed(self._too_big(max_bytes))
                    name = _file_name(response, url)
                    target = work_dir / name
                    size = 0
                    with target.open("wb") as out:
                        for chunk in response.iter_bytes(1 << 16):
                            size += len(chunk)
                            if size > max_bytes:
                                raise ValidationFailed(self._too_big(max_bytes))
                            out.write(chunk)
                    if size == 0:
                        raise ValidationFailed("The link gave an empty file.")
                    return target, name, kind or mimetypes.guess_type(name)[0] or "application/octet-stream"
        raise ValidationFailed("The link redirected too many times.")

    @staticmethod
    def _too_big(max_bytes: int) -> str:
        return f"That file is bigger than your plan's {max_bytes // (1024 * 1024)} MB limit."
