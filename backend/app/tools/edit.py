"""Edit tools: watermark, page numbers, headers/footers, Bates numbering, metadata, bookmarks, crop, flatten."""

import datetime as dt
from functools import lru_cache
from pathlib import Path
from typing import Literal

import pikepdf
from pydantic import BaseModel, Field
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from app.domain.errors import ValidationFailed
from app.tools.base import Category, Tool, ToolContext, ToolOptions, stem
from app.tools.overlay import MM, anchor_xy, color, decode_image, stamp_pages, visible_box
from app.tools.pages import parse_page_set
from app.tools.pdfio import open_pdf, save_pdf
from app.tools.registry import register

Position = Literal[
    "top-left", "top-center", "top-right",
    "center",
    "bottom-left", "bottom-center", "bottom-right",
]  # fmt: skip

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)


@lru_cache
def text_font() -> str:
    """A Unicode TrueType font if one is installed, otherwise the built-in Helvetica (Latin-1 only)."""
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).exists():
            pdfmetrics.registerFont(TTFont("FolioSans", candidate))
            return "FolioSans"
    return "Helvetica"


def _text_width(text: str, size: float) -> float:
    return pdfmetrics.stringWidth(text, text_font(), size)


@register
class WatermarkTool(Tool):
    id = "watermark"
    name = "Add watermark"
    description = "Stamp text or an image over your pages, once or tiled."
    category = Category.EDIT

    class Options(ToolOptions):
        text: str | None = Field("CONFIDENTIAL", max_length=200)
        image: str | None = Field(None, description="Image as a data URL; used instead of text when set")
        font_size: float = Field(48, ge=4, le=400)
        color: str = "#ef4444"
        opacity: float = Field(0.3, ge=0.02, le=1.0)
        rotation: float = Field(45, ge=-180, le=180)
        position: Position = "center"
        tiled: bool = Field(False, description="Repeat the watermark across the page")
        image_scale: float = Field(0.4, gt=0, le=1, description="Image width as a share of the page width")
        pages: str = "all"

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        if not options.text and not options.image:
            raise ValidationFailed("Enter watermark text or choose an image.")
        image = decode_image(options.image) if options.image else None
        fill = color(options.color)

        def draw(c: Canvas, _index: int, w: float, h: float) -> None:
            c.saveState()
            c.setFillAlpha(options.opacity)
            c.setStrokeAlpha(options.opacity)
            c.setFillColor(fill)
            if image is not None:
                iw, ih = image.getSize()
                box_w = w * options.image_scale
                box_h = box_w * ih / iw
            else:
                c.setFont(text_font(), options.font_size)
                box_w, box_h = _text_width(options.text, options.font_size), options.font_size

            def stamp_at(cx: float, cy: float) -> None:
                c.saveState()
                c.translate(cx, cy)
                c.rotate(options.rotation)
                if image is not None:
                    c.drawImage(image, -box_w / 2, -box_h / 2, box_w, box_h, mask="auto")
                else:
                    c.drawCentredString(0, -box_h / 3, options.text)
                c.restoreState()

            if options.tiled:
                step_x, step_y = box_w + 80, box_h + 120
                y = step_y / 2
                while y < h + step_y:
                    x = step_x / 2
                    while x < w + step_x:
                        stamp_at(x, y)
                        x += step_x
                    y += step_y
            else:
                x, y = anchor_xy(options.position, box_w, box_h, w, h, 36)
                stamp_at(x + box_w / 2, y + box_h / 2)
            c.restoreState()

        return _stamp_each(inputs, ctx, draw, options.pages, "watermarked")


def _stamp_each(inputs: list[Path], ctx: ToolContext, draw, pages: str, suffix: str) -> list[Path]:
    outputs = []
    for path in inputs:
        with open_pdf(path) as pdf:
            stamp_pages(pdf, draw, parse_page_set(pages, len(pdf.pages)))
            outputs.append(save_pdf(pdf, ctx.output_path(f"{stem(path)}-{suffix}.pdf")))
    return outputs


def _expand(template: str, *, page: int, total: int, filename: str) -> str:
    return (
        template.replace("{page}", str(page))
        .replace("{n}", str(page))
        .replace("{total}", str(total))
        .replace("{date}", dt.date.today().isoformat())
        .replace("{filename}", filename)
    )


@register
class PageNumbersTool(Tool):
    id = "page_numbers"
    name = "Add page numbers"
    description = "Number your pages, with the position, style and start you want."
    category = Category.EDIT

    class Options(ToolOptions):
        position: Position = "bottom-center"
        template: str = Field("{page}", description="Use {page} and {total}, e.g. 'Page {page} of {total}'")
        start_at: int = Field(1, description="Number shown on the first numbered page")
        pages: str = "all"
        skip_first: bool = Field(False, description="Don't number the cover page")
        font_size: float = Field(11, ge=4, le=72)
        color: str = "#111827"
        margin_mm: float = Field(10, ge=0, le=100)

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        fill = color(options.color)
        outputs = []
        for path in inputs:
            with open_pdf(path) as pdf:
                selected = sorted(parse_page_set(options.pages, len(pdf.pages)))
                if options.skip_first and selected and selected[0] == 0:
                    selected = selected[1:]
                numbers = {index: options.start_at + n for n, index in enumerate(selected)}
                total = options.start_at + len(selected) - 1

                def draw(c: Canvas, index: int, w: float, h: float) -> None:
                    text = _expand(options.template, page=numbers[index], total=total, filename=path.stem)  # noqa: B023
                    c.setFont(text_font(), options.font_size)
                    c.setFillColor(fill)
                    tw = _text_width(text, options.font_size)
                    x, y = anchor_xy(options.position, tw, options.font_size, w, h, options.margin_mm * MM)
                    c.drawString(x, y, text)

                stamp_pages(pdf, draw, set(selected))
                outputs.append(save_pdf(pdf, ctx.output_path(f"{stem(path)}-numbered.pdf")))
        return outputs


@register
class HeaderFooterTool(Tool):
    id = "header_footer"
    name = "Header & footer"
    description = "Add text to the top and bottom of pages, with page numbers, dates and file names."
    category = Category.EDIT

    class Options(ToolOptions):
        header_left: str = ""
        header_center: str = ""
        header_right: str = ""
        footer_left: str = ""
        footer_center: str = Field("", description="Tokens: {page}, {total}, {date}, {filename}")
        footer_right: str = "{page} / {total}"
        font_size: float = Field(9, ge=4, le=48)
        color: str = "#374151"
        margin_mm: float = Field(10, ge=0, le=100)
        pages: str = "all"

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        fill = color(options.color)
        slots = {
            "top-left": options.header_left,
            "top-center": options.header_center,
            "top-right": options.header_right,
            "bottom-left": options.footer_left,
            "bottom-center": options.footer_center,
            "bottom-right": options.footer_right,
        }
        if not any(slots.values()):
            raise ValidationFailed("Enter some header or footer text.")
        outputs = []
        for path in inputs:
            with open_pdf(path) as pdf:
                total = len(pdf.pages)

                def draw(c: Canvas, index: int, w: float, h: float) -> None:
                    c.setFont(text_font(), options.font_size)
                    c.setFillColor(fill)
                    for position, template in slots.items():
                        if not template:
                            continue
                        text = _expand(template, page=index + 1, total=total, filename=path.stem)  # noqa: B023
                        tw = _text_width(text, options.font_size)
                        x, y = anchor_xy(position, tw, options.font_size, w, h, options.margin_mm * MM)
                        c.drawString(x, y, text)

                stamp_pages(pdf, draw, parse_page_set(options.pages, total))
                outputs.append(save_pdf(pdf, ctx.output_path(f"{stem(path)}.pdf")))
        return outputs


@register
class BatesTool(Tool):
    id = "bates"
    name = "Bates numbering"
    description = "Stamp sequential legal identifiers across one or many documents."
    category = Category.EDIT

    class Options(ToolOptions):
        prefix: str = Field("DOC-", max_length=40)
        suffix: str = Field("", max_length=40)
        start: int = Field(1, ge=0)
        digits: int = Field(6, ge=1, le=12)
        position: Position = "bottom-right"
        font_size: float = Field(10, ge=4, le=48)
        color: str = "#111827"
        margin_mm: float = Field(8, ge=0, le=100)

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        fill = color(options.color)
        counter = options.start
        outputs = []
        for path in inputs:  # numbering continues across files, in upload order
            with open_pdf(path) as pdf:
                first = counter

                def draw(c: Canvas, index: int, w: float, h: float, first=first) -> None:
                    text = f"{options.prefix}{first + index:0{options.digits}d}{options.suffix}"
                    c.setFont(text_font(), options.font_size)
                    c.setFillColor(fill)
                    tw = _text_width(text, options.font_size)
                    x, y = anchor_xy(options.position, tw, options.font_size, w, h, options.margin_mm * MM)
                    c.drawString(x, y, text)

                stamp_pages(pdf, draw)
                counter += len(pdf.pages)
                outputs.append(save_pdf(pdf, ctx.output_path(f"{stem(path)}-bates.pdf")))
        return outputs


@register
class CropTool(Tool):
    id = "crop"
    name = "Crop PDF"
    description = "Trim page margins."
    category = Category.EDIT

    class Options(ToolOptions):
        top_mm: float = Field(10, ge=0)
        right_mm: float = Field(10, ge=0)
        bottom_mm: float = Field(10, ge=0)
        left_mm: float = Field(10, ge=0)
        pages: str = "all"

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        outputs = []
        for path in inputs:
            with open_pdf(path) as pdf:
                for i in parse_page_set(options.pages, len(pdf.pages)):
                    page = pdf.pages[i]
                    x0, y0, x1, y1 = visible_box(page)
                    box = (
                        x0 + options.left_mm * MM,
                        y0 + options.bottom_mm * MM,
                        x1 - options.right_mm * MM,
                        y1 - options.top_mm * MM,
                    )
                    if box[2] - box[0] < 10 or box[3] - box[1] < 10:
                        raise ValidationFailed(f"The margins are larger than page {i + 1}.")
                    page.cropbox = pikepdf.Array(box)
                    page.obj.TrimBox = pikepdf.Array(box)
                outputs.append(save_pdf(pdf, ctx.output_path(f"{stem(path)}-cropped.pdf")))
        return outputs


@register
class EditMetadataTool(Tool):
    id = "edit_metadata"
    name = "Edit metadata"
    description = "Change or wipe the title, author, subject and keywords."
    category = Category.EDIT

    class Options(ToolOptions):
        title: str | None = None
        author: str | None = None
        subject: str | None = None
        keywords: str | None = None
        creator: str | None = None
        remove_all: bool = Field(False, description="Strip all metadata first (privacy)")

    FIELDS = {
        "title": "/Title",
        "author": "/Author",
        "subject": "/Subject",
        "keywords": "/Keywords",
        "creator": "/Creator",
    }

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        outputs = []
        for path in inputs:
            with open_pdf(path) as pdf:
                if options.remove_all:
                    if "/Metadata" in pdf.Root:
                        del pdf.Root.Metadata
                    pdf.docinfo = pdf.make_indirect(pikepdf.Dictionary())
                for field, key in self.FIELDS.items():
                    value = getattr(options, field)
                    if value is not None:
                        pdf.docinfo[key] = value
                if "/Metadata" in pdf.Root:
                    del pdf.Root.Metadata  # stale XMP would contradict the new docinfo
                outputs.append(save_pdf(pdf, ctx.output_path(f"{stem(path)}.pdf")))
        return outputs


class Bookmark(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    page: int = Field(..., ge=1)
    level: int = Field(0, ge=0, le=5, description="Nesting depth, 0 = top level")


@register
class CreateBookmarksTool(Tool):
    id = "create_bookmarks"
    name = "Create bookmarks"
    description = "Add a clickable table of contents (outline)."
    category = Category.EDIT
    max_files = 1

    class Options(ToolOptions):
        bookmarks: list[Bookmark] = Field(..., min_length=1)
        replace_existing: bool = True

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        with open_pdf(inputs[0]) as pdf:
            total = len(pdf.pages)
            with pdf.open_outline() as outline:
                if options.replace_existing:
                    outline.root.clear()
                stack: list[list[pikepdf.OutlineItem]] = [outline.root]
                for mark in options.bookmarks:
                    if mark.page > total:
                        raise ValidationFailed(f"Bookmark '{mark.title}' points past the last page ({total}).")
                    item = pikepdf.OutlineItem(mark.title, mark.page - 1)
                    level = min(mark.level, len(stack) - 1)
                    del stack[level + 1 :]
                    stack[level].append(item)
                    stack.append(item.children)
            return [save_pdf(pdf, ctx.output_path(f"{stem(inputs[0])}.pdf"))]


@register
class DeleteAnnotationsTool(Tool):
    id = "delete_annotations"
    name = "Delete annotations"
    description = "Remove comments, highlights, stamps and other markup."
    category = Category.EDIT

    class Options(ToolOptions):
        keep_links: bool = Field(True, description="Keep clickable links")
        keep_form_fields: bool = Field(True, description="Keep fillable form fields")

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        outputs = []
        for path in inputs:
            with open_pdf(path) as pdf:
                for page in pdf.pages:
                    annots = page.obj.get("/Annots")
                    if annots is None:
                        continue
                    kept = [a for a in annots if self._keep(a, options)]
                    if kept:
                        page.obj.Annots = pdf.make_indirect(pikepdf.Array(kept))
                    else:
                        del page.obj.Annots
                outputs.append(save_pdf(pdf, ctx.output_path(f"{stem(path)}-clean.pdf")))
        return outputs

    @staticmethod
    def _keep(annot, options) -> bool:
        subtype = annot.get("/Subtype")
        return (options.keep_links and subtype == "/Link") or (options.keep_form_fields and subtype == "/Widget")


@register
class FlattenTool(Tool):
    id = "flatten"
    name = "Flatten PDF"
    description = "Burn form fields and annotations into the page so they can't be changed."
    category = Category.EDIT

    def run(self, inputs: list[Path], options, ctx: ToolContext) -> list[Path]:
        outputs = []
        for path in inputs:
            with open_pdf(path) as pdf:
                pdf.generate_appearance_streams()
                pdf.flatten_annotations(mode="all")
                if "/AcroForm" in pdf.Root:
                    del pdf.Root.AcroForm
                outputs.append(save_pdf(pdf, ctx.output_path(f"{stem(path)}-flat.pdf")))
        return outputs


class Placement(BaseModel):
    """Where to draw a signature, as fractions of the visible page (0,0 = top-left, as on screen)."""

    page: int = Field(..., ge=1)
    x: float = Field(..., ge=0, le=1)
    y: float = Field(..., ge=0, le=1)
    width: float = Field(..., gt=0, le=1)


@register
class SignTool(Tool):
    id = "sign"
    name = "Sign PDF"
    description = "Draw, type or upload your signature and place it anywhere, on as many pages as you need."
    category = Category.SECURITY
    max_files = 1

    class Options(ToolOptions):
        signature: str = Field(..., description="Signature image as a data URL (drawn, typed or uploaded)")
        placements: list[Placement] = Field(..., min_length=1)
        add_date: bool = Field(False, description="Print today's date under the signature")
        flatten: bool = Field(True, description="Flatten so the signature can't be moved")

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        image = decode_image(options.signature)
        iw, ih = image.getSize()
        by_page: dict[int, list[Placement]] = {}
        for p in options.placements:
            by_page.setdefault(p.page - 1, []).append(p)
        with open_pdf(inputs[0]) as pdf:
            for index in by_page:
                if index >= len(pdf.pages):
                    raise ValidationFailed(f"Page {index + 1} doesn't exist.")

            def draw(c: Canvas, index: int, w: float, h: float) -> None:
                for p in by_page[index]:
                    box_w = p.width * w
                    box_h = box_w * ih / iw
                    x = p.x * w
                    y = h - p.y * h - box_h  # screen coordinates have y pointing down
                    c.drawImage(image, x, y, box_w, box_h, mask="auto")
                    if options.add_date:
                        c.setFont(text_font(), 9)
                        c.drawString(x, y - 11, dt.date.today().strftime("%d %b %Y"))

            stamp_pages(pdf, draw, set(by_page))
            if options.flatten:
                pdf.flatten_annotations(mode="all")
            return [save_pdf(pdf, ctx.output_path(f"{stem(inputs[0])}-signed.pdf"))]
