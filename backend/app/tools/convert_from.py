"""Convert from PDF: images, Office formats, text, Markdown and PDF/A."""

import statistics
from pathlib import Path
from typing import Literal

import pdfplumber
import pikepdf
import pypdfium2 as pdfium
from openpyxl import Workbook
from pydantic import Field

from app.domain.errors import ToolFailed, ValidationFailed
from app.tools.base import Category, Tool, ToolContext, ToolOptions, stem
from app.tools.pages import parse_page_list
from app.tools.registry import register


def render_pages(path: Path, dpi: int, pages: str = "all"):
    """Yield (page_number, PIL image) for the selected pages."""
    doc = pdfium.PdfDocument(path)
    try:
        for index in parse_page_list(pages, len(doc)):
            page = doc[index]
            yield index + 1, page.render(scale=dpi / 72).to_pil()
            page.close()
    finally:
        doc.close()


@register
class PdfToImagesTool(Tool):
    id = "pdf_to_images"
    name = "PDF to JPG"
    description = "Turn each page into a JPG or PNG image."
    category = Category.CONVERT_FROM
    browser_capable = True
    produces_pdf = False

    class Options(ToolOptions):
        format: Literal["jpg", "png"] = "jpg"
        dpi: int = Field(150, ge=36, le=600, description="Image resolution")
        quality: int = Field(90, ge=30, le=100, description="JPG quality")
        pages: str = "all"

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        outputs = []
        for path in inputs:
            for number, image in render_pages(path, options.dpi, options.pages):
                out = ctx.output_path(f"{stem(path)}-page-{number:03d}.{options.format}")
                if options.format == "jpg":
                    image.convert("RGB").save(out, "JPEG", quality=options.quality, optimize=True)
                else:
                    image.save(out, "PNG", optimize=True)
                outputs.append(out)
        return outputs


@register
class PdfToWordTool(Tool):
    id = "pdf_to_word"
    name = "PDF to Word"
    description = "Convert PDFs into editable DOCX documents."
    category = Category.CONVERT_FROM
    premium = True
    produces_pdf = False

    def run(self, inputs: list[Path], options, ctx: ToolContext) -> list[Path]:
        # Imported lazily: pdf2docx pulls in PyMuPDF (AGPL), see docs/RESEARCH.md "License watch-outs".
        from pdf2docx import Converter

        outputs = []
        for path in inputs:
            out = ctx.output_path(f"{stem(path)}.docx")
            converter = Converter(str(path))
            try:
                converter.convert(str(out), multi_processing=False)
            except Exception as exc:
                raise ToolFailed(f"Could not convert '{path.name}' to Word.") from exc
            finally:
                converter.close()
            outputs.append(out)
        return outputs


@register
class PdfToPowerPointTool(Tool):
    id = "pdf_to_powerpoint"
    name = "PDF to PowerPoint"
    description = "Turn each page into a slide in a PPTX deck."
    category = Category.CONVERT_FROM
    premium = True
    produces_pdf = False

    def run(self, inputs: list[Path], options, ctx: ToolContext) -> list[Path]:
        from pptx import Presentation
        from pptx.util import Emu

        outputs = []
        for path in inputs:
            deck = Presentation()
            blank = deck.slide_layouts[6]
            for number, image in render_pages(path, 200):
                if number == 1:
                    # EMU: 914400 per inch; slides take the first page's aspect ratio.
                    deck.slide_width = Emu(int(image.width / 200 * 914400))
                    deck.slide_height = Emu(int(image.height / 200 * 914400))
                img_path = ctx.output_path(f"slide-{number}.png")
                image.save(img_path, "PNG")
                slide = deck.slides.add_slide(blank)
                slide.shapes.add_picture(str(img_path), 0, 0, deck.slide_width, deck.slide_height)
                notes_text = _page_text(path, number - 1)
                if notes_text:
                    slide.notes_slide.notes_text_frame.text = notes_text
            out = ctx.output_path(f"{stem(path)}.pptx")
            deck.save(out)
            outputs.append(out)
        return outputs


def _page_text(path: Path, index: int) -> str:
    with pdfplumber.open(path) as pdf:
        return (pdf.pages[index].extract_text() or "").strip()


@register
class PdfToExcelTool(Tool):
    id = "pdf_to_excel"
    name = "PDF to Excel"
    description = "Pull tables out of PDFs into an XLSX spreadsheet."
    category = Category.CONVERT_FROM
    premium = True
    produces_pdf = False

    class Options(ToolOptions):
        sheet_per: Literal["page", "table"] = Field("page", description="One sheet per page or per table")

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        outputs = []
        for path in inputs:
            wb = Workbook()
            wb.remove(wb.active)
            with pdfplumber.open(path) as pdf:
                for p_index, page in enumerate(pdf.pages, start=1):
                    tables = page.extract_tables() or []
                    if not tables:
                        # No ruled table: fall back to text rows split on wide gaps.
                        tables = [_text_rows(page)] if page.extract_text() else []
                    if options.sheet_per == "page" and tables:
                        ws = wb.create_sheet(f"Page {p_index}")
                        for t_index, table in enumerate(tables):
                            if t_index:
                                ws.append([])
                            for row in table:
                                ws.append([_cell(c) for c in row])
                    else:
                        for t_index, table in enumerate(tables, start=1):
                            ws = wb.create_sheet(f"P{p_index} T{t_index}"[:31])
                            for row in table:
                                ws.append([_cell(c) for c in row])
            if not wb.sheetnames:
                raise ValidationFailed(f"No tables or text found in '{path.name}'. Try OCR first if it's a scan.")
            out = ctx.output_path(f"{stem(path)}.xlsx")
            wb.save(out)
            outputs.append(out)
        return outputs


def _text_rows(page) -> list[list[str]]:
    rows = []
    for line in (page.extract_text(layout=True) or "").splitlines():
        cells = [c.strip() for c in line.split("  ") if c.strip()]
        if cells:
            rows.append(cells)
    return rows


def _cell(value):
    if value is None:
        return None
    text = str(value).strip()
    try:
        return float(text.replace(",", "")) if text.replace(",", "").replace(".", "", 1).lstrip("-").isdigit() else text
    except ValueError:
        return text


@register
class PdfToTextTool(Tool):
    id = "pdf_to_text"
    name = "PDF to Text"
    description = "Extract all text into a plain .txt file."
    category = Category.CONVERT_FROM
    produces_pdf = False

    class Options(ToolOptions):
        keep_layout: bool = Field(False, description="Keep the visual layout with spaces")

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        outputs = []
        for path in inputs:
            with pdfplumber.open(path) as pdf:
                text = "\n\f\n".join((p.extract_text(layout=options.keep_layout) or "") for p in pdf.pages)
            out = ctx.output_path(f"{stem(path)}.txt")
            out.write_text(text, encoding="utf-8")
            outputs.append(out)
        return outputs


def pdf_to_markdown(path: Path) -> str:
    """Heuristic Markdown: larger-than-body lines become headings, everything else paragraphs."""
    blocks: list[str] = []
    with pdfplumber.open(path) as pdf:
        lines: list[tuple[float, str]] = []
        for page in pdf.pages:
            words = page.extract_words(extra_attrs=["size"], keep_blank_chars=False, use_text_flow=True)
            current_top, current, sizes = None, [], []
            for w in words:
                if current_top is not None and abs(w["top"] - current_top) > 2:
                    lines.append((max(sizes), " ".join(current)))
                    current, sizes = [], []
                current_top = w["top"]
                current.append(w["text"])
                sizes.append(w["size"])
            if current:
                lines.append((max(sizes), " ".join(current)))
            lines.append((0, ""))  # page break
        body = statistics.median([s for s, t in lines if t]) if any(t for _, t in lines) else 0
        paragraph: list[str] = []
        for size, text in lines:
            heading = body and size >= body * 1.15 and len(text) < 120
            if (not text or heading) and paragraph:
                blocks.append(" ".join(paragraph))
                paragraph = []
            if heading:
                level = 1 if size >= body * 1.6 else 2 if size >= body * 1.3 else 3
                blocks.append(f"{'#' * level} {text}")
            elif text:
                paragraph.append(text)
        if paragraph:
            blocks.append(" ".join(paragraph))
    return "\n\n".join(blocks).strip() + "\n"


@register
class PdfToMarkdownTool(Tool):
    id = "pdf_to_markdown"
    name = "PDF to Markdown"
    description = "Extract text with headings as Markdown, ready for docs or AI tools."
    category = Category.CONVERT_FROM
    produces_pdf = False

    def run(self, inputs: list[Path], options, ctx: ToolContext) -> list[Path]:
        outputs = []
        for path in inputs:
            out = ctx.output_path(f"{stem(path)}.md")
            out.write_text(pdf_to_markdown(path), encoding="utf-8")
            outputs.append(out)
        return outputs


@register
class PdfToPdfaTool(Tool):
    id = "pdf_to_pdfa"
    name = "PDF to PDF/A"
    description = "Convert to PDF/A for long-term archiving."
    category = Category.CONVERT_FROM
    premium = True

    class Options(ToolOptions):
        part: Literal[1, 2, 3] = Field(2, description="PDF/A conformance part (2 is the common choice)")

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        return [ctx.gs().pdfa(p, ctx.output_path(f"{stem(p)}-pdfa.pdf"), options.part) for p in inputs]


@register
class ExtractImagesTool(Tool):
    id = "extract_images"
    name = "Extract images"
    description = "Save every embedded image at its original quality."
    category = Category.CONVERT_FROM
    produces_pdf = False

    class Options(ToolOptions):
        min_size_px: int = Field(32, ge=1, description="Skip images smaller than this (icons, lines)")

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        outputs: list[Path] = []
        for path in inputs:
            seen: set[tuple[int, int]] = set()
            with pikepdf.open(path) as pdf:
                for p_index, page in enumerate(pdf.pages, start=1):
                    for name, raw in page.images.items():
                        if raw.objgen in seen:
                            continue
                        seen.add(raw.objgen)
                        image = pikepdf.PdfImage(raw)
                        if min(image.width, image.height) < options.min_size_px:
                            continue
                        target = ctx.output_path(f"{stem(path)}-p{p_index}-{str(name).lstrip('/')}")
                        try:
                            outputs.append(Path(image.extract_to(fileprefix=str(target))))
                        except Exception:
                            pil = image.as_pil_image()
                            png = target.with_suffix(".png")
                            pil.save(png)
                            outputs.append(png)
        if not outputs:
            raise ValidationFailed("No images found in this PDF.")
        return outputs
