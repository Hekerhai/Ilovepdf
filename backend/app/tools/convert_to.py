"""Convert to PDF: images, Office documents and web pages."""

import ipaddress
import socket
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import img2pdf
from PIL import Image, ImageOps
from pydantic import Field

from app.domain.errors import ValidationFailed
from app.tools.base import IMAGES, Category, Tool, ToolContext, ToolOptions, stem
from app.tools.organize import PAGE_SIZES_PT
from app.tools.overlay import MM
from app.tools.registry import register


class ImagesOptions(ToolOptions):
    page_size: Literal["fit", "A4", "Letter"] = Field("fit", description="'fit' makes each page the size of its image")
    orientation: Literal["auto", "portrait", "landscape"] = "auto"
    margin_mm: float = Field(0, ge=0, le=50)
    single_file: bool = Field(True, description="One PDF with all images, or one PDF per image")


def _normalize_image(path: Path, work: Path, index: int) -> Path:
    """img2pdf embeds JPEG/PNG losslessly but rejects alpha channels and some formats; normalize those."""
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        if image.format == "JPEG" and image.mode in ("RGB", "L", "CMYK"):
            return path
        if image.mode in ("RGBA", "LA", "P"):
            rgba = image.convert("RGBA")
            background = Image.new("RGB", rgba.size, "white")
            background.paste(rgba, mask=rgba.split()[-1])
            image = background
        elif image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        out = work / f"img-{index:04d}.png"
        image.save(out, "PNG")
        return out


def images_to_pdf(inputs: list[Path], output: Path, options: ImagesOptions) -> Path:
    work = output.parent
    normalized = [_normalize_image(p, work, i) for i, p in enumerate(inputs)]
    if options.page_size == "fit":
        border = options.margin_mm * MM
        layout = img2pdf.get_layout_fun(None, None, (border, border) if border else None)
    else:
        w, h = PAGE_SIZES_PT[options.page_size]
        layout = _sized_layout(w, h, options.orientation, options.margin_mm * MM)
    output.write_bytes(
        img2pdf.convert([str(p) for p in normalized], layout_fun=layout, rotation=img2pdf.Rotation.ifvalid)
    )
    return output


def _sized_layout(w: float, h: float, orientation: str, margin: float):
    def layout(img_w_px, img_h_px, ndpi):
        img_w = img_w_px * 72 / ndpi[0]
        img_h = img_h_px * 72 / ndpi[1]
        landscape = orientation == "landscape" or (orientation == "auto" and img_w > img_h)
        page_w, page_h = (max(w, h), min(w, h)) if landscape else (min(w, h), max(w, h))
        scale = min((page_w - 2 * margin) / img_w, (page_h - 2 * margin) / img_h)
        return page_w, page_h, img_w * scale, img_h * scale

    return layout


@register
class ImagesToPdfTool(Tool):
    id = "images_to_pdf"
    name = "JPG to PDF"
    description = "Turn photos and scans (JPG, PNG, WebP, TIFF...) into a PDF."
    category = Category.CONVERT_TO
    accepts = IMAGES
    browser_capable = True
    Options = ImagesOptions

    def run(self, inputs: list[Path], options: ImagesOptions, ctx: ToolContext) -> list[Path]:
        if options.single_file:
            return [images_to_pdf(inputs, ctx.output_path(f"{stem(inputs[0])}.pdf"), options)]
        return [images_to_pdf([p], ctx.output_path(f"{stem(p)}.pdf"), options) for p in inputs]


class _OfficeToPdf(Tool):
    category = Category.CONVERT_TO

    def run(self, inputs: list[Path], options, ctx: ToolContext) -> list[Path]:
        converter = ctx.require_converter()
        return [converter.office_to_pdf(p, ctx.output_path(f"{stem(p)}.pdf")) for p in inputs]


@register
class WordToPdfTool(_OfficeToPdf):
    id = "word_to_pdf"
    name = "Word to PDF"
    description = "Convert DOC, DOCX, ODT and RTF documents to PDF."
    accepts = (".doc", ".docx", ".odt", ".rtf", ".txt")


@register
class PowerPointToPdfTool(_OfficeToPdf):
    id = "powerpoint_to_pdf"
    name = "PowerPoint to PDF"
    description = "Convert PPT, PPTX and ODP presentations to PDF."
    accepts = (".ppt", ".pptx", ".odp", ".pps", ".ppsx")


@register
class ExcelToPdfTool(_OfficeToPdf):
    id = "excel_to_pdf"
    name = "Excel to PDF"
    description = "Convert XLS, XLSX, ODS and CSV spreadsheets to PDF."
    accepts = (".xls", ".xlsx", ".ods", ".csv")


@register
class HtmlToPdfTool(Tool):
    id = "html_to_pdf"
    name = "HTML to PDF"
    description = "Turn a web page (URL) or an HTML file into a PDF."
    category = Category.CONVERT_TO
    accepts = (".html", ".htm")
    min_files = 0
    max_files = 1

    class Options(ToolOptions):
        url: str | None = Field(None, description="A public web address, used when no file is uploaded")

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        converter = ctx.require_converter()
        if inputs:
            return [converter.html_to_pdf(output=ctx.output_path(f"{stem(inputs[0])}.pdf"), html_file=inputs[0])]
        if not options.url:
            raise ValidationFailed("Upload an HTML file or enter a URL.")
        url = validate_public_url(options.url)
        host = urlparse(url).hostname or "page"
        return [converter.html_to_pdf(output=ctx.output_path(f"{host}.pdf"), url=url)]


def validate_public_url(url: str) -> str:
    """Reject non-HTTP schemes and private/internal addresses (SSRF protection)."""
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValidationFailed("Enter a valid http(s) URL.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        raise ValidationFailed(f"Could not resolve '{parsed.hostname}'.") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ValidationFailed("That address is not publicly reachable.")
    return url
