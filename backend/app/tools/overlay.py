"""Draw on top of existing pages (watermarks, page numbers, signatures...).

``stamp_pages`` gives the caller a ReportLab canvas in *visual* coordinates: origin at the bottom-left of the page
as the reader sees it, with page rotation already accounted for.
"""

import base64
import io
import re
from collections.abc import Callable

import pikepdf
from PIL import Image
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from app.domain.errors import ValidationFailed

DrawFn = Callable[[Canvas, int, float, float], None]

MM = 72 / 25.4


def visible_box(page: pikepdf.Page) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = (float(v) for v in page.cropbox)
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def visual_size(page: pikepdf.Page) -> tuple[float, float]:
    x0, y0, x1, y1 = visible_box(page)
    w, h = x1 - x0, y1 - y0
    return (h, w) if _rotation(page) in (90, 270) else (w, h)


def _rotation(page: pikepdf.Page) -> int:
    return int(page.obj.get("/Rotate", 0)) % 360


def stamp_pages(pdf: pikepdf.Pdf, draw: DrawFn, pages: set[int] | None = None) -> None:
    targets = [i for i in range(len(pdf.pages)) if pages is None or i in pages]
    if not targets:
        return
    buf = io.BytesIO()
    canvas = Canvas(buf)
    for index in targets:
        page = pdf.pages[index]
        # Draw upright at the visual size; add_overlay (qpdf) counter-rotates the overlay to match /Rotate.
        vw, vh = visual_size(page)
        canvas.setPageSize((vw, vh))
        draw(canvas, index, vw, vh)
        canvas.showPage()
    canvas.save()
    buf.seek(0)
    with pikepdf.open(buf) as overlay:
        for overlay_page, index in zip(overlay.pages, targets, strict=True):
            page = pdf.pages[index]
            page.add_overlay(overlay_page, pikepdf.Rectangle(*visible_box(page)))


def color(value: str) -> HexColor:
    if not re.fullmatch(r"#?[0-9a-fA-F]{6}", value):
        raise ValidationFailed(f"'{value}' is not a hex colour like #1f2937.")
    return HexColor("#" + value.lstrip("#"))


def decode_image(data_url: str) -> ImageReader:
    """Accept a data URL or bare base64 string and return a ReportLab image."""
    payload = data_url.split(",", 1)[1] if data_url.startswith("data:") else data_url
    try:
        raw = base64.b64decode(payload, validate=False)
        image = Image.open(io.BytesIO(raw))
        image.load()
    except Exception:
        raise ValidationFailed("The image could not be read. Use a PNG or JPG.") from None
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA")
    return ImageReader(image)


def anchor_xy(
    position: str, box_w: float, box_h: float, page_w: float, page_h: float, margin: float
) -> tuple[float, float]:
    """Bottom-left corner for a box placed at a named position, e.g. ``bottom-center``."""
    vertical, _, horizontal = position.partition("-")
    if vertical == "center" and not horizontal:
        horizontal = "center"
    x = {"left": margin, "center": (page_w - box_w) / 2, "right": page_w - box_w - margin}[horizontal]
    y = {"bottom": margin, "center": (page_h - box_h) / 2, "top": page_h - box_h - margin}[vertical]
    return x, y


def visual_to_user(page: pikepdf.Page) -> Callable[[float, float], tuple[float, float]]:
    """Map visual coordinates (bottom-left origin, as the reader sees the page) to PDF user space.

    Needed when writing objects that live in user space directly, such as form widgets, rather than through
    ``stamp_pages``. Mirrors ``visualToUser`` in the web app's browser handlers.
    """
    x0, y0, x1, y1 = visible_box(page)
    w, h = x1 - x0, y1 - y0
    rotation = _rotation(page)
    if rotation == 90:
        return lambda X, Y: (x0 + w - Y, y0 + X)
    if rotation == 180:
        return lambda X, Y: (x0 + w - X, y0 + h - Y)
    if rotation == 270:
        return lambda X, Y: (x0 + Y, y0 + h - X)
    return lambda X, Y: (x0 + X, y0 + Y)


def user_rect(page: pikepdf.Page, x: float, y: float, width: float, height: float) -> list[float]:
    """A box given as fractions of the visual page (top-left origin, as on screen) in user-space PDF coordinates."""
    vw, vh = visual_size(page)
    to_user = visual_to_user(page)
    ax, ay = to_user(x * vw, vh - y * vh)
    bx, by = to_user((x + width) * vw, vh - (y + height) * vh)
    return [min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)]


def page_rotation(page: pikepdf.Page) -> int:
    return _rotation(page)
