"""Convert to PDF: images, Office documents and web pages."""

import ipaddress
import socket
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import img2pdf
import numpy as np
from PIL import Image, ImageFilter, ImageOps
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


class ScanOptions(ImagesOptions):
    page_size: Literal["fit", "A4", "Letter"] = Field("A4", description="'fit' makes each page the size of its photo")
    filter: Literal["color", "grayscale", "enhanced", "black_white"] = Field(
        "enhanced", description="'enhanced' evens out lighting and sharpens text, like a scanner"
    )


def clean_scan(path: Path, out: Path, mode: str) -> Path:
    """Make a phone photo of a document look scanned: even lighting, crisp text, white paper."""
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    if mode == "color":
        image = ImageOps.autocontrast(image, cutoff=1)
        image.save(out, "JPEG", quality=88)
        return out
    gray = image.convert("L")
    if mode == "grayscale":
        ImageOps.autocontrast(gray, cutoff=1).save(out, "JPEG", quality=88)
        return out
    # Divide by a heavily blurred copy to remove shadows and uneven light, then stretch the contrast.
    radius = max(gray.size) // 30 or 1
    background = gray.filter(ImageFilter.GaussianBlur(radius))
    ratio = np.asarray(gray, dtype=np.float32) * 245 / np.maximum(np.asarray(background, dtype=np.float32), 1)
    flat = Image.fromarray(np.clip(ratio, 0, 255).astype(np.uint8))
    flat = ImageOps.autocontrast(flat, cutoff=(2, 1)).filter(ImageFilter.UnsharpMask(radius=2, percent=120))
    if mode == "black_white":
        out = out.with_suffix(".png")
        flat.point(lambda v: 255 if v > 165 else 0, mode="1").save(out, "PNG", optimize=True)
        return out
    flat.save(out, "JPEG", quality=85)
    return out


@register
class ScanToPdfTool(Tool):
    id = "scan_to_pdf"
    name = "Scan to PDF"
    description = "Snap pages with your camera and get a clean, scanner-quality PDF."
    category = Category.CONVERT_TO
    accepts = IMAGES
    browser_capable = True
    Options = ScanOptions

    def run(self, inputs: list[Path], options: ScanOptions, ctx: ToolContext) -> list[Path]:
        scans = [clean_scan(p, ctx.work_dir / f"scan-{i:04d}.jpg", options.filter) for i, p in enumerate(inputs)]
        name = f"{stem(inputs[0])}-scan.pdf"
        if options.single_file:
            return [images_to_pdf(scans, ctx.output_path(name), options)]
        return [
            images_to_pdf([p], ctx.output_path(f"{stem(src)}-scan.pdf"), options)
            for p, src in zip(scans, inputs, strict=True)
        ]


class _OfficeToPdf(Tool):
    category = Category.CONVERT_TO

    def run(self, inputs: list[Path], options, ctx: ToolContext) -> list[Path]:
        converter = ctx.require_converter()
        return [converter.office_to_pdf(p, ctx.output_path(f"{stem(p)}.pdf")) for p in inputs]


@register
class WordToPdfTool(_OfficeToPdf):
    id = "word_to_pdf"
    name = "Word to PDF"
    description = "Convert Word, OpenDocument, RTF, text and Apple Pages documents to PDF."
    accepts = (".doc", ".docx", ".odt", ".rtf", ".txt", ".pages", ".wpd", ".wps")


@register
class PowerPointToPdfTool(_OfficeToPdf):
    id = "powerpoint_to_pdf"
    name = "PowerPoint to PDF"
    description = "Convert PowerPoint, OpenDocument and Apple Keynote presentations to PDF."
    accepts = (".ppt", ".pptx", ".odp", ".pps", ".ppsx", ".key")


@register
class ExcelToPdfTool(_OfficeToPdf):
    id = "excel_to_pdf"
    name = "Excel to PDF"
    description = "Convert Excel, OpenDocument, CSV and Apple Numbers spreadsheets to PDF."
    accepts = (".xls", ".xlsx", ".ods", ".csv", ".numbers")


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


EBOOKS = (".epub", ".mobi", ".fb2", ".xps", ".oxps", ".cbz")


def ebook_to_pdf(path: Path, out: Path, page_size: str = "A4", font_size: float = 11) -> Path:
    """Reflow an ebook onto pages with MuPDF. Comic archives (CBZ) and XPS keep their own page sizes."""
    import pymupdf

    try:
        doc = pymupdf.open(path)
    except Exception:
        raise ValidationFailed(f"'{path.name}' couldn't be read. It may be damaged or DRM-protected.") from None
    try:
        if doc.is_reflowable:
            width, height = PAGE_SIZES_PT[page_size]
            doc.layout(width=width, height=height, fontsize=font_size)
        pdf = pymupdf.open("pdf", doc.convert_to_pdf())
        if doc.metadata:
            pdf.set_metadata({k: v for k, v in doc.metadata.items() if k in ("title", "author", "subject") and v})
        toc = doc.get_toc()
        if toc:
            pdf.set_toc(toc)
        pdf.save(out, garbage=3, deflate=True)
        return out
    finally:
        doc.close()


@register
class EbookToPdfTool(Tool):
    id = "ebook_to_pdf"
    name = "Ebook to PDF"
    description = "Convert EPUB, MOBI, FB2, XPS and CBZ comic files to PDF, keeping the table of contents."
    category = Category.CONVERT_TO
    accepts = EBOOKS

    class Options(ToolOptions):
        page_size: Literal["A4", "Letter", "A5"] = Field("A4", description="Page size for reflowed books")
        font_size: float = Field(11, ge=6, le=24, description="Text size for reflowed books, in points")

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        return [
            ebook_to_pdf(p, ctx.output_path(f"{stem(p)}.pdf"), options.page_size, options.font_size) for p in inputs
        ]


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


ZIP_MAX_FILES = 300
ZIP_MAX_BYTES = 1024 * 1024 * 1024
OFFICE = tuple(sorted({*WordToPdfTool.accepts, *PowerPointToPdfTool.accepts, *ExcelToPdfTool.accepts, ".html", ".htm"}))


@register
class ZipToPdfTool(Tool):
    id = "zip_to_pdf"
    name = "ZIP to PDF"
    description = "Convert every PDF, image, Office file and ebook inside a ZIP and combine them into one PDF."
    category = Category.CONVERT_TO
    accepts = (".zip",)
    max_files = 1

    class Options(ToolOptions):
        bookmarks: bool = Field(True, description="Add a bookmark for each file")
        list_skipped: bool = Field(True, description="End with a page naming files that couldn't be converted")
        page_size: Literal["fit", "A4", "Letter"] = Field("A4", description="Page size for images and ebooks")

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        import zipfile

        import pikepdf

        work = ctx.work_dir / "unzipped"
        work.mkdir()
        try:
            archive = zipfile.ZipFile(inputs[0])
        except zipfile.BadZipFile:
            raise ValidationFailed("This ZIP file is damaged.") from None
        with archive:
            entries = [
                e
                for e in archive.infolist()
                if not e.is_dir() and not Path(e.filename).name.startswith(".") and "__MACOSX" not in e.filename
            ]
            if len(entries) > ZIP_MAX_FILES:
                raise ValidationFailed(f"The ZIP holds {len(entries)} files; the limit is {ZIP_MAX_FILES}.")
            if sum(e.file_size for e in entries) > ZIP_MAX_BYTES:
                raise ValidationFailed("The ZIP unpacks to more than 1 GB, which is over the limit.")
            entries.sort(key=lambda e: e.filename.lower())
            converted: list[tuple[str, Path]] = []
            skipped: list[str] = []
            for index, entry in enumerate(entries):
                # Never trust names inside an archive: extract to our own flat names.
                suffix = Path(entry.filename).suffix.lower()
                local = work / f"{index:04d}{suffix}"
                with archive.open(entry) as src, local.open("wb") as dst:
                    while chunk := src.read(1 << 20):
                        dst.write(chunk)
                title = Path(entry.filename).stem
                try:
                    pdf = self._convert(local, suffix, options, ctx, index)
                except ValidationFailed:
                    skipped.append(entry.filename)
                    continue
                if pdf is None:
                    skipped.append(entry.filename)
                else:
                    converted.append((title, pdf))
        if not converted:
            raise ValidationFailed(
                "Nothing in this ZIP could be converted. It needs PDFs, images, Office files or ebooks."
            )

        if skipped and options.list_skipped:
            converted.append(("Files not included", self._skipped_page(skipped, ctx.work_dir / "skipped.pdf")))
        out = ctx.output_path(f"{stem(inputs[0])}.pdf")
        with pikepdf.new() as merged:
            starts: list[tuple[str, int]] = []
            for title, pdf in converted:
                with pikepdf.open(pdf) as part:
                    starts.append((title, len(merged.pages)))
                    merged.pages.extend(part.pages)
            if options.bookmarks:
                with merged.open_outline() as outline:
                    outline.root.extend(pikepdf.OutlineItem(title, page) for title, page in starts)
            merged.save(out)
        return [out]

    @staticmethod
    def _skipped_page(names: list[str], out: Path) -> Path:
        from xml.sax.saxutils import escape

        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate

        styles = getSampleStyleSheet()
        story = [Paragraph("Files not included", styles["Heading2"])]
        story += [Paragraph(escape(n), styles["BodyText"]) for n in names]
        SimpleDocTemplate(str(out), pagesize=A4).build(story)
        return out

    @staticmethod
    def _convert(path: Path, suffix: str, options: Options, ctx: ToolContext, index: int) -> Path | None:
        out = ctx.work_dir / f"part-{index:04d}.pdf"
        if suffix == ".pdf":
            import pikepdf

            try:
                with pikepdf.open(path):
                    return path
            except pikepdf.PdfError:
                raise ValidationFailed(f"{path.name} is damaged") from None
        if suffix in IMAGES:
            return images_to_pdf([path], out, ImagesOptions(page_size=options.page_size))
        if suffix in EBOOKS:
            return ebook_to_pdf(path, out, "A4" if options.page_size == "fit" else options.page_size)
        if suffix in (".html", ".htm"):
            return ctx.require_converter().html_to_pdf(output=out, html_file=path)
        if suffix in OFFICE:
            return ctx.require_converter().office_to_pdf(path, out)
        return None
