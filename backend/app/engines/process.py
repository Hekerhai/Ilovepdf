"""Run external engines (Ghostscript, LibreOffice...) as isolated subprocesses."""

import logging
import subprocess

from app.domain.errors import ToolFailed

log = logging.getLogger(__name__)


def run(cmd: list[str], *, timeout: int, error: str) -> None:
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
    except FileNotFoundError:
        raise ToolFailed(f"{error} The '{cmd[0]}' engine is not installed on this server.") from None
    except subprocess.TimeoutExpired:
        raise ToolFailed(f"{error} The operation took too long.") from None
    if result.returncode != 0:
        log.warning("%s failed (%s): %s", cmd[0], result.returncode, result.stderr[-2000:])
        raise ToolFailed(error)
