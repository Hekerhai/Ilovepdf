"""Opening and saving PDFs with consistent, user-readable errors."""

from pathlib import Path

import pikepdf

from app.domain.errors import ValidationFailed


def open_pdf(path: Path, password: str = "") -> pikepdf.Pdf:
    try:
        return pikepdf.open(path, password=password or "")
    except pikepdf.PasswordError:
        raise ValidationFailed(
            f"'{path.name}' is password protected. Unlock it first or enter its password.",
            code="password_required",
        ) from None
    except pikepdf.PdfError:
        raise ValidationFailed(f"'{path.name}' is not a readable PDF. Try the Repair tool.") from None


def save_pdf(pdf: pikepdf.Pdf, path: Path, **kwargs) -> Path:
    pdf.save(
        path,
        compress_streams=True,
        object_stream_mode=pikepdf.ObjectStreamMode.generate,
        **kwargs,
    )
    return path
