"""Organize tools: merge, split, reorder, rotate, and other page-level operations."""

import io
from enum import StrEnum
from pathlib import Path
from typing import Literal

import pikepdf
from pydantic import BaseModel, Field
from pypdf import PdfReader

from app.domain.errors import ValidationFailed
from app.tools.base import Category, Tool, ToolContext, ToolOptions, stem
from app.tools.overlay import MM, visible_box, visual_size
from app.tools.pages import parse_page_list, parse_page_set, parse_range_groups
from app.tools.pdfio import open_pdf, save_pdf
from app.tools.registry import register

PAGE_SIZES_PT = {
    "A3": (297 * MM, 420 * MM),
    "A4": (210 * MM, 297 * MM),
    "A5": (148 * MM, 210 * MM),
    "Letter": (612.0, 792.0),
    "Legal": (612.0, 1008.0),
}


def _write_pages(src: pikepdf.Pdf, indexes: list[int], path: Path) -> Path:
    out = pikepdf.new()
    for i in indexes:
        out.pages.append(src.pages[i])
    return save_pdf(out, path)


@register
class MergeTool(Tool):
    id = "merge"
    name = "Merge PDF"
    description = "Combine several PDFs into one, in the order you choose."
    category = Category.ORGANIZE
    min_files = 2
    browser_capable = True

    class Options(ToolOptions):
        add_bookmarks: bool = Field(True, description="Add a bookmark for each merged file")

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        out = pikepdf.new()
        bookmarks: list[tuple[str, int]] = []
        for path in inputs:
            with open_pdf(path) as src:
                bookmarks.append((stem(path), len(out.pages)))
                out.pages.extend(src.pages)
        if options.add_bookmarks:
            with out.open_outline() as outline:
                for title, page in bookmarks:
                    outline.root.append(pikepdf.OutlineItem(title, page))
        return [save_pdf(out, ctx.output_path("merged.pdf"))]


class SplitMode(StrEnum):
    RANGES = "ranges"
    EVERY = "every"
    SIZE = "size"
    BOOKMARKS = "bookmarks"
    ALL = "all"


@register
class SplitTool(Tool):
    id = "split"
    name = "Split PDF"
    description = "Split by page ranges, every N pages, file size or bookmarks."
    category = Category.ORGANIZE
    max_files = 1
    browser_capable = True

    class Options(ToolOptions):
        mode: SplitMode = Field(SplitMode.RANGES, description="How to split")
        ranges: str = Field("1-1", description="Page ranges, one file per range, e.g. 1-3, 4-8, 9-")
        every: int = Field(1, ge=1, description="Pages per file (for 'every' mode)")
        max_size_mb: float = Field(5.0, gt=0, description="Max size per file in MB (for 'size' mode)")
        merge_output: bool = Field(False, description="Put all extracted ranges into a single PDF")

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        path = inputs[0]
        with open_pdf(path) as src:
            total = len(src.pages)
            groups = self._groups(path, src, options, total)
            if options.merge_output and options.mode == SplitMode.RANGES:
                merged = [i for g in groups for i in g]
                return [_write_pages(src, merged, ctx.output_path(f"{stem(path)}-extracted.pdf"))]
            return [
                _write_pages(src, g, ctx.output_path(f"{stem(path)}-{n + 1:03d}.pdf")) for n, g in enumerate(groups)
            ]

    def _groups(self, path: Path, src: pikepdf.Pdf, o: Options, total: int) -> list[list[int]]:
        match o.mode:
            case SplitMode.RANGES:
                return parse_range_groups(o.ranges, total)
            case SplitMode.EVERY:
                return [list(range(i, min(i + o.every, total))) for i in range(0, total, o.every)]
            case SplitMode.ALL:
                return [[i] for i in range(total)]
            case SplitMode.SIZE:
                return _groups_by_size(src, int(o.max_size_mb * 1024 * 1024))
            case SplitMode.BOOKMARKS:
                return _groups_by_bookmarks(path, total)


def _groups_by_size(src: pikepdf.Pdf, limit: int) -> list[list[int]]:
    groups: list[list[int]] = []
    current: list[int] = []
    for i in range(len(src.pages)):
        candidate = current + [i]
        if current and _size_of(src, candidate) > limit:
            groups.append(current)
            current = [i]
        else:
            current = candidate
    if current:
        groups.append(current)
    return groups


def _size_of(src: pikepdf.Pdf, indexes: list[int]) -> int:
    out = pikepdf.new()
    for i in indexes:
        out.pages.append(src.pages[i])
    buf = io.BytesIO()
    out.save(buf, compress_streams=True)
    return buf.tell()


def _groups_by_bookmarks(path: Path, total: int) -> list[list[int]]:
    reader = PdfReader(path)
    starts = sorted({reader.get_destination_page_number(item) for item in reader.outline if not isinstance(item, list)})
    if not starts:
        raise ValidationFailed("This PDF has no bookmarks to split by.")
    if starts[0] != 0:
        starts.insert(0, 0)
    bounds = starts + [total]
    return [list(range(a, b)) for a, b in zip(bounds, bounds[1:], strict=False) if b > a]


@register
class SplitInHalfTool(Tool):
    id = "split_in_half"
    name = "Split in half"
    description = "Cut each page into two, for scanned book spreads."
    category = Category.ORGANIZE
    max_files = 1

    class Options(ToolOptions):
        direction: Literal["vertical", "horizontal"] = Field(
            "vertical", description="Vertical gives left/right halves, horizontal gives top/bottom"
        )

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        with open_pdf(inputs[0]) as src:
            out = pikepdf.new()
            for page in src.pages:
                x0, y0, x1, y1 = visible_box(page)
                if options.direction == "vertical":
                    halves = [(x0, y0, (x0 + x1) / 2, y1), ((x0 + x1) / 2, y0, x1, y1)]
                else:
                    halves = [(x0, (y0 + y1) / 2, x1, y1), (x0, y0, x1, (y0 + y1) / 2)]
                for box in halves:
                    out.pages.append(page)
                    copy = out.pages[-1]
                    copy.mediabox = pikepdf.Array(box)
                    copy.cropbox = pikepdf.Array(box)
            return [save_pdf(out, ctx.output_path(f"{stem(inputs[0])}-halves.pdf"))]


class _PageSelectOptions(ToolOptions):
    pages: str = Field(..., description="Pages, e.g. 1, 3-5, 9-")


@register
class RemovePagesTool(Tool):
    id = "remove_pages"
    name = "Remove pages"
    description = "Delete the pages you don't need."
    category = Category.ORGANIZE
    max_files = 1
    browser_capable = True
    Options = _PageSelectOptions

    def run(self, inputs: list[Path], options: _PageSelectOptions, ctx: ToolContext) -> list[Path]:
        with open_pdf(inputs[0]) as src:
            drop = parse_page_set(options.pages, len(src.pages))
            keep = [i for i in range(len(src.pages)) if i not in drop]
            if not keep:
                raise ValidationFailed("You can't remove every page.")
            return [_write_pages(src, keep, ctx.output_path(f"{stem(inputs[0])}.pdf"))]


@register
class ExtractPagesTool(Tool):
    id = "extract_pages"
    name = "Extract pages"
    description = "Pull selected pages out into a new PDF."
    category = Category.ORGANIZE
    max_files = 1
    browser_capable = True
    Options = _PageSelectOptions

    def run(self, inputs: list[Path], options: _PageSelectOptions, ctx: ToolContext) -> list[Path]:
        with open_pdf(inputs[0]) as src:
            pages = parse_page_list(options.pages, len(src.pages))
            return [_write_pages(src, pages, ctx.output_path(f"{stem(inputs[0])}-pages.pdf"))]


class PageRef(BaseModel):
    file: int = Field(0, ge=0, description="Index of the input file")
    page: int | None = Field(None, ge=1, description="1-based page number; omit for a blank page")
    rotate: Literal[0, 90, 180, 270] = 0


@register
class OrganizeTool(Tool):
    id = "organize"
    name = "Organize PDF"
    description = "Reorder, rotate, delete and add blank pages, across one or more files."
    category = Category.ORGANIZE
    browser_capable = True

    class Options(ToolOptions):
        pages: list[PageRef] = Field(..., min_length=1, description="The final page order")

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        sources = [open_pdf(p) for p in inputs]
        try:
            out = pikepdf.new()
            for ref in options.pages:
                if ref.file >= len(sources):
                    raise ValidationFailed(f"File #{ref.file + 1} was not uploaded.")
                src = sources[ref.file]
                if ref.page is None:
                    w, h = visual_size(src.pages[0]) if len(src.pages) else PAGE_SIZES_PT["A4"]
                    out.add_blank_page(page_size=(w, h))
                else:
                    if ref.page > len(src.pages):
                        raise ValidationFailed(f"Page {ref.page} doesn't exist in file #{ref.file + 1}.")
                    out.pages.append(src.pages[ref.page - 1])
                if ref.rotate:
                    out.pages[-1].rotate(ref.rotate, relative=True)
            return [save_pdf(out, ctx.output_path(f"{stem(inputs[0])}-organized.pdf"))]
        finally:
            for s in sources:
                s.close()


@register
class RotateTool(Tool):
    id = "rotate"
    name = "Rotate PDF"
    description = "Rotate all pages or just the ones you pick."
    category = Category.ORGANIZE
    browser_capable = True

    class Options(ToolOptions):
        angle: Literal[90, 180, 270] = Field(90, description="Clockwise rotation")
        pages: str = Field("all", description="Pages to rotate")

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        outputs = []
        for path in inputs:
            with open_pdf(path) as pdf:
                for i in parse_page_set(options.pages, len(pdf.pages)):
                    pdf.pages[i].rotate(options.angle, relative=True)
                outputs.append(save_pdf(pdf, ctx.output_path(f"{stem(path)}.pdf")))
        return outputs


@register
class FlipTool(Tool):
    id = "flip"
    name = "Flip PDF"
    description = "Mirror pages horizontally or vertically."
    category = Category.ORGANIZE

    class Options(ToolOptions):
        direction: Literal["horizontal", "vertical"] = "horizontal"
        pages: str = "all"

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        outputs = []
        for path in inputs:
            with open_pdf(path) as pdf:
                for i in parse_page_set(options.pages, len(pdf.pages)):
                    page = pdf.pages[i]
                    x0, y0, x1, y1 = (float(v) for v in page.mediabox)
                    if options.direction == "horizontal":
                        matrix = f"-1 0 0 1 {x0 + x1} 0 cm"
                    else:
                        matrix = f"1 0 0 -1 0 {y0 + y1} cm"
                    page.contents_coalesce()
                    page.contents_add(pikepdf.Stream(pdf, f"q {matrix}\n".encode()), prepend=True)
                    page.contents_add(pikepdf.Stream(pdf, b"\nQ"))
                outputs.append(save_pdf(pdf, ctx.output_path(f"{stem(path)}-flipped.pdf")))
        return outputs


@register
class AlternateMixTool(Tool):
    id = "alternate_mix"
    name = "Alternate & mix"
    description = "Interleave pages from several files, e.g. separately scanned fronts and backs."
    category = Category.ORGANIZE
    min_files = 2

    class Options(ToolOptions):
        reverse_last: bool = Field(False, description="Reverse the last file (backs scanned in reverse order)")
        pages_per_take: int = Field(1, ge=1, description="Pages to take from each file in turn")

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        sources = [open_pdf(p) for p in inputs]
        try:
            orders = [list(range(len(s.pages))) for s in sources]
            if options.reverse_last:
                orders[-1].reverse()
            out = pikepdf.new()
            cursor = [0] * len(sources)
            n = options.pages_per_take
            while any(cursor[i] < len(orders[i]) for i in range(len(sources))):
                for i, src in enumerate(sources):
                    for idx in orders[i][cursor[i] : cursor[i] + n]:
                        out.pages.append(src.pages[idx])
                    cursor[i] += n
            return [save_pdf(out, ctx.output_path("mixed.pdf"))]
        finally:
            for s in sources:
                s.close()


@register
class NUpTool(Tool):
    id = "n_up"
    name = "N-up"
    description = "Print several pages per sheet."
    category = Category.ORGANIZE
    max_files = 1

    class Options(ToolOptions):
        per_sheet: Literal[2, 4, 6, 8, 9, 16] = 4
        sheet_size: Literal["A4", "A3", "Letter", "Legal"] = "A4"
        margin_mm: float = Field(5, ge=0, le=50)

    LAYOUTS = {2: (2, 1), 4: (2, 2), 6: (3, 2), 8: (4, 2), 9: (3, 3), 16: (4, 4)}

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        cols, rows = self.LAYOUTS[options.per_sheet]
        sw, sh = PAGE_SIZES_PT[options.sheet_size]
        if cols > rows:  # landscape sheets for 2-up style layouts
            sw, sh = sh, sw
        m = options.margin_mm * MM
        cell_w, cell_h = (sw - m * (cols + 1)) / cols, (sh - m * (rows + 1)) / rows
        with open_pdf(inputs[0]) as src:
            out = pikepdf.new()
            for start in range(0, len(src.pages), options.per_sheet):
                sheet = out.add_blank_page(page_size=(sw, sh))
                for k, page in enumerate(src.pages[start : start + options.per_sheet]):
                    col, row = k % cols, k // cols
                    x = m + col * (cell_w + m)
                    y = sh - m - (row + 1) * cell_h - row * m
                    sheet.add_overlay(out.copy_foreign(page.obj), pikepdf.Rectangle(x, y, x + cell_w, y + cell_h))
            return [save_pdf(out, ctx.output_path(f"{stem(inputs[0])}-{options.per_sheet}up.pdf"))]


@register
class ResizeTool(Tool):
    id = "resize"
    name = "Resize pages"
    description = "Fit every page onto a standard paper size, keeping proportions."
    category = Category.ORGANIZE

    class Options(ToolOptions):
        size: Literal["A3", "A4", "A5", "Letter", "Legal"] = "A4"
        margin_mm: float = Field(0, ge=0, le=50)

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        tw, th = PAGE_SIZES_PT[options.size]
        m = options.margin_mm * MM
        outputs = []
        for path in inputs:
            with open_pdf(path) as src:
                out = pikepdf.new()
                for page in src.pages:
                    vw, vh = visual_size(page)
                    w, h = (th, tw) if vw > vh else (tw, th)  # keep each page's orientation
                    sheet = out.add_blank_page(page_size=(w, h))
                    sheet.add_overlay(out.copy_foreign(page.obj), pikepdf.Rectangle(m, m, w - m, h - m))
                outputs.append(save_pdf(out, ctx.output_path(f"{stem(path)}-{options.size}.pdf")))
        return outputs
