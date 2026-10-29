"""Security tools: protect, unlock, compare."""

import difflib
import html
import re
from pathlib import Path
from typing import Literal

import pdfplumber
import pikepdf
from pydantic import BaseModel, Field

from app.domain.errors import ValidationFailed
from app.tools.base import Category, Tool, ToolContext, ToolOptions, stem
from app.tools.pdfio import open_pdf, save_pdf
from app.tools.registry import register


@register
class ProtectTool(Tool):
    id = "protect"
    name = "Protect PDF"
    description = "Encrypt with a password (AES-256) and control printing, copying and editing."
    category = Category.SECURITY

    class Options(ToolOptions):
        password: str = Field(..., min_length=1, max_length=127, description="Password to open the file")
        owner_password: str | None = Field(
            None, max_length=127, description="Separate password for changing permissions"
        )
        allow_print: bool = True
        allow_copy: bool = True
        allow_modify: bool = False
        allow_annotate: bool = True
        allow_fill_forms: bool = True

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        permissions = pikepdf.Permissions(
            print_lowres=options.allow_print,
            print_highres=options.allow_print,
            extract=options.allow_copy,
            accessibility=True,
            modify_other=options.allow_modify,
            modify_assembly=options.allow_modify,
            modify_annotation=options.allow_annotate,
            modify_form=options.allow_fill_forms,
        )
        encryption = pikepdf.Encryption(
            user=options.password,
            owner=options.owner_password or options.password,
            R=6,
            allow=permissions,
        )
        outputs = []
        for path in inputs:
            with open_pdf(path) as pdf:
                outputs.append(save_pdf(pdf, ctx.output_path(f"{stem(path)}-protected.pdf"), encryption=encryption))
        return outputs


@register
class UnlockTool(Tool):
    id = "unlock"
    name = "Unlock PDF"
    description = "Remove the password and restrictions from a PDF you have the right to open."
    category = Category.SECURITY

    class Options(ToolOptions):
        password: str = Field("", max_length=127, description="Needed only if the file asks for one to open")

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        outputs = []
        for path in inputs:
            try:
                pdf = pikepdf.open(path, password=options.password)
            except pikepdf.PasswordError:
                raise ValidationFailed(f"Wrong password for '{path.name}'.", code="password_required") from None
            with pdf:
                outputs.append(save_pdf(pdf, ctx.output_path(f"{stem(path)}-unlocked.pdf"), encryption=False))
        return outputs


@register
class CompareTool(Tool):
    id = "compare"
    name = "Compare PDF"
    description = "See every text change between two versions, side by side."
    category = Category.SECURITY
    min_files = 2
    max_files = 2
    premium = True
    produces_pdf = False

    class Options(ToolOptions):
        ignore_whitespace: bool = True
        ignore_case: bool = False

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        old, new = (self._lines(p, options) for p in inputs)
        stats = {"added": 0, "removed": 0}
        for op in difflib.ndiff(old, new):
            if op.startswith("+ "):
                stats["added"] += 1
            elif op.startswith("- "):
                stats["removed"] += 1
        table = difflib.HtmlDiff(wrapcolumn=80).make_table(
            old, new, html.escape(inputs[0].name), html.escape(inputs[1].name), context=True, numlines=2
        )
        report = _REPORT.format(
            a=html.escape(inputs[0].name),
            b=html.escape(inputs[1].name),
            added=stats["added"],
            removed=stats["removed"],
            table=table if (stats["added"] or stats["removed"]) else "<p>No text differences found.</p>",
        )
        out = ctx.output_path(f"compare-{stem(inputs[0])}-vs-{stem(inputs[1])}.html")
        out.write_text(report, encoding="utf-8")
        return [out]

    @staticmethod
    def _lines(path: Path, options: Options) -> list[str]:
        open_pdf(path).close()  # consistent error for encrypted / broken files
        lines: list[str] = []
        with pdfplumber.open(path) as pdf:
            for number, page in enumerate(pdf.pages, start=1):
                for line in (page.extract_text() or "").splitlines():
                    if options.ignore_whitespace:
                        line = " ".join(line.split())
                    if options.ignore_case:
                        line = line.lower()
                    if line:
                        lines.append(line)
                lines.append(f"── page {number} ──")
        return lines


_REPORT = """<!doctype html><html><head><meta charset="utf-8"><title>Compare: {a} vs {b}</title>
<style>
body{{font:14px system-ui,sans-serif;margin:24px;color:#111827}}
h1{{font-size:20px}} .stats span{{margin-right:16px;font-weight:600}}
.add{{color:#047857}} .rem{{color:#b91c1c}}
table.diff{{border-collapse:collapse;width:100%;font:12px ui-monospace,monospace}}
table.diff td{{padding:2px 6px;vertical-align:top}}
.diff_add{{background:#d1fae5}} .diff_chg{{background:#fef3c7}} .diff_sub{{background:#fee2e2}}
.diff_header{{color:#6b7280}} .diff_next{{display:none}}
</style></head><body>
<h1>{a} → {b}</h1>
<p class="stats"><span class="add">+{added} lines added</span><span class="rem">−{removed} lines removed</span></p>
{table}
</body></html>"""


class RedactArea(BaseModel):
    """A box to black out, as fractions of the visible page (0,0 = top-left, as on screen)."""

    page: int = Field(..., ge=1)
    x: float = Field(..., ge=0, le=1)
    y: float = Field(..., ge=0, le=1)
    width: float = Field(..., gt=0, le=1)
    height: float = Field(..., gt=0, le=1)


@register
class RedactTool(Tool):
    id = "redact"
    name = "Redact PDF"
    description = "Permanently remove sensitive text and areas, not just cover them."
    category = Category.SECURITY
    premium = True

    class Options(ToolOptions):
        terms: list[str] = Field(default_factory=list, description="Words or phrases to remove everywhere")
        patterns: list[Literal["email", "phone", "credit_card", "iban", "ssn"]] = Field(
            default_factory=list, description="Common sensitive data to find automatically"
        )
        areas: list[RedactArea] = Field(default_factory=list)
        remove_metadata: bool = True

    PATTERNS = {
        "email": r"[\w.+-]+@[\w-]+\.[\w.-]+",
        "phone": r"\+?\d[\d ()-]{7,}\d",
        "credit_card": r"\b(?:\d[ -]?){13,16}\b",
        "iban": r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b",
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    }

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        # PyMuPDF (AGPL) does true content removal; see docs/RESEARCH.md "License watch-outs".
        import pymupdf

        if not (options.terms or options.patterns or options.areas):
            raise ValidationFailed("Choose words, patterns or areas to redact.")
        regexes = [re.compile(self.PATTERNS[p]) for p in options.patterns]
        outputs = []
        for path in inputs:
            open_pdf(path).close()
            doc = pymupdf.open(path)
            try:
                hits = 0
                for index, page in enumerate(doc):
                    rects = [r for term in options.terms if term.strip() for r in page.search_for(term.strip())]
                    if regexes:
                        text = page.get_text()
                        for rx in regexes:
                            for match in {m.group(0) for m in rx.finditer(text)}:
                                rects.extend(page.search_for(match))
                    box = page.rect
                    for area in options.areas:
                        if area.page == index + 1:
                            rects.append(pymupdf.Rect(
                                box.x0 + area.x * box.width,
                                box.y0 + area.y * box.height,
                                box.x0 + (area.x + area.width) * box.width,
                                box.y0 + (area.y + area.height) * box.height,
                            ) * page.derotation_matrix)  # fmt: skip
                    for rect in rects:
                        page.add_redact_annot(rect, fill=(0, 0, 0))
                    if rects:
                        hits += len(rects)
                        page.apply_redactions()
                if options.remove_metadata:
                    doc.set_metadata({})
                    doc.del_xml_metadata()
                out = ctx.output_path(f"{stem(path)}-redacted.pdf")
                doc.save(out, garbage=4, deflate=True, clean=True)
            finally:
                doc.close()
            outputs.append(out)
        return outputs
