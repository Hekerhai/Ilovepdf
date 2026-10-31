"""Accessibility check: how well a PDF works with screen readers, with concrete fixes. Can also fix the basics."""

from pathlib import Path

import pdfplumber
import pikepdf
from pydantic import Field

from app.tools.base import PDF, Category, Tool, ToolContext, ToolOptions, stem
from app.tools.organize import PLACEHOLDER_TITLES
from app.tools.pdfio import open_pdf, save_pdf
from app.tools.registry import register

PASS, WARN, FAIL = "Pass", "Needs attention", "Fails"
FONT_FILES = ("/FontFile", "/FontFile2", "/FontFile3")


def _title(pdf: pikepdf.Pdf) -> str:
    title = str(pdf.docinfo.get("/Title", "") or "").strip()
    if not title:
        try:
            with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
                title = str(meta.get("dc:title", "") or "").strip()
        except Exception:
            title = ""
    return "" if title.lower() in PLACEHOLDER_TITLES else title


def _walk_struct(node, found: dict, depth: int = 0) -> None:
    if depth > 200 or not isinstance(node, pikepdf.Dictionary):
        return
    kind = node.get("/S")
    if kind == "/Figure":
        found["figures"] += 1
        if node.get("/Alt") or node.get("/ActualText"):
            found["with_alt"] += 1
    if kind in ("/H", "/H1", "/H2", "/H3", "/H4", "/H5", "/H6"):
        found["headings"] += 1
    kids = node.get("/K")
    if isinstance(kids, pikepdf.Array):
        for kid in kids:
            _walk_struct(kid, found, depth + 1)
    elif isinstance(kids, pikepdf.Dictionary):
        _walk_struct(kids, found, depth + 1)


def check(path: Path) -> tuple[list[tuple[str, str, str]], dict]:
    """Returns (check name, result, detail and fix) rows, plus facts used by the fixer."""
    rows: list[tuple[str, str, str]] = []
    with open_pdf(path) as pdf:
        root = pdf.Root
        pages = len(pdf.pages)
        title = _title(pdf)
        display_title = bool(root.get("/ViewerPreferences", {}).get("/DisplayDocTitle", False))
        rows.append(
            ("Document title", PASS if title and display_title else (WARN if title else FAIL),
             f"Title is “{title}”." + ("" if display_title else " Readers show the file name instead; turn on "
              "'display document title'.") if title else "No title. Screen readers announce the file name instead. "
             "Set one with Edit metadata, or use Fix the basics.")
        )  # fmt: skip
        lang = str(root.get("/Lang", "") or "")
        rows.append(("Language", PASS if lang else FAIL,
                     f"Language is {lang}." if lang else "No document language, so screen readers may use the wrong "
                     "voice and pronunciation. Fix the basics sets it."))  # fmt: skip

        marked = bool(root.get("/MarkInfo", {}).get("/Marked", False))
        struct = root.get("/StructTreeRoot")
        found = {"figures": 0, "with_alt": 0, "headings": 0}
        if struct is not None:
            _walk_struct(struct, found)
        tagged = marked and struct is not None
        rows.append(("Tags (reading order and structure)", PASS if tagged else FAIL,
                     "The document is tagged." if tagged else "Untagged: screen readers can't tell headings, lists, "
                     "tables and reading order apart. Re-export from the source app with 'tagged PDF' or "
                     "'accessibility' turned on (Word: Save as PDF > Options > Document structure tags)."))  # fmt: skip
        if tagged:
            rows.append(("Headings", PASS if found["headings"] else WARN,
                         f"{found['headings']} tagged headings." if found["headings"] else
                         "No tagged headings, so readers can't jump between sections."))  # fmt: skip

        images = 0
        no_text: list[int] = []
        with pdfplumber.open(path) as plumber:
            for i, page in enumerate(plumber.pages, start=1):
                images += len(page.images)
                if len((page.extract_text() or "").strip()) < 5:
                    no_text.append(i)
        if no_text:
            shown = ", ".join(map(str, no_text[:15])) + ("…" if len(no_text) > 15 else "")
            result = FAIL if len(no_text) == pages else WARN
            rows.append(("Real text (not pictures of text)", result,
                         f"{len(no_text)} of {pages} pages have no text a screen reader can read (pages {shown}). "
                         "If they are scans, run OCR PDF."))  # fmt: skip
        else:
            rows.append(("Real text (not pictures of text)", PASS, "Every page has readable text."))
        if images:
            if tagged and found["figures"]:
                missing = found["figures"] - found["with_alt"]
                rows.append(("Alternative text for images", PASS if not missing else FAIL,
                             "Every tagged figure has alternative text." if not missing else
                             f"{missing} of {found['figures']} figures have no alternative text. Add it in the "
                             "source document and export again."))  # fmt: skip
            else:
                rows.append(
                    (
                        "Alternative text for images",
                        WARN,
                        f"{images} images, but without tags there's no way to give them alternative text.",
                    )
                )

        unembedded: set[str] = set()
        for page in pdf.pages:
            fonts = page.get("/Resources", {}).get("/Font", {})
            for font in fonts.values() if isinstance(fonts, pikepdf.Dictionary) else []:
                descriptors = [font.get("/FontDescriptor")]
                for desc in font.get("/DescendantFonts", []) or []:
                    descriptors.append(desc.get("/FontDescriptor"))
                for d in descriptors:
                    if isinstance(d, pikepdf.Dictionary) and not any(
                        k in d for k in ("/FontFile", "/FontFile2", "/FontFile3")
                    ):
                        unembedded.add(str(font.get("/BaseFont", "?")).lstrip("/"))
        rows.append(("Fonts embedded", PASS if not unembedded else WARN,
                     "All fonts are embedded." if not unembedded else
                     f"Not embedded: {', '.join(sorted(unembedded)[:8])}. Text may look different on other devices; "
                     "PDF to PDF/A embeds them."))  # fmt: skip

        if pages >= 20:
            has_outline = bool(root.get("/Outlines") and root.Outlines.get("/First"))
            rows.append(
                (
                    "Bookmarks",
                    PASS if has_outline else WARN,
                    "Has bookmarks."
                    if has_outline
                    else f"{pages} pages and no bookmarks. Add them with Create bookmarks so people can navigate.",
                )
            )

        fields = root.get("/AcroForm", {}).get("/Fields", []) if "/AcroForm" in root else []
        if fields:
            unlabeled = sum(1 for f in fields if isinstance(f, pikepdf.Dictionary) and not f.get("/TU"))
            rows.append(("Form field labels", PASS if not unlabeled else WARN,
                         "Every form field has a label." if not unlabeled else
                         f"{unlabeled} of {len(fields)} form fields have no tooltip, which screen readers use as "
                         "the field's label."))  # fmt: skip

        if pdf.is_encrypted:
            ok = pdf.allow.accessibility if hasattr(pdf.allow, "accessibility") else True
            rows.append(
                (
                    "Security settings",
                    PASS if ok else FAIL,
                    "Assistive technology may read the content."
                    if ok
                    else "The security settings block screen readers. Remove the restriction with Unlock PDF.",
                )
            )

        first_line = ""
        with pdfplumber.open(path) as plumber:
            if plumber.pages:
                first_line = next(
                    (ln.strip() for ln in (plumber.pages[0].extract_text() or "").splitlines() if ln.strip()), ""
                )
    return rows, {"title": title, "first_line": first_line[:120], "lang": lang}


def report(name: str, rows: list[tuple[str, str, str]], fixed: list[str] | None = None) -> str:
    fails = sum(r[1] == FAIL for r in rows)
    warns = sum(r[1] == WARN for r in rows)
    verdict = "No problems found." if not fails and not warns else f"{fails} failed, {warns} need attention."
    lines = [
        f"# Accessibility check: {name}",
        "",
        verdict,
        "",
        "| Check | Result | Details and how to fix |",
        "| --- | --- | --- |",
    ]
    lines += [f"| {c} | {r} | {d.replace('|', '/')} |" for c, r, d in rows]
    if fixed:
        lines += ["", "## Fixed in the attached PDF", ""] + [f"- {f}" for f in fixed]
    lines += ["", "Checks follow the main PDF/UA and WCAG 2.2 requirements that can be tested automatically. "
              "A person should still review reading order and alternative text."]  # fmt: skip
    return "\n".join(lines) + "\n"


@register
class AccessibilityCheckTool(Tool):
    id = "accessibility_check"
    name = "Accessibility check"
    description = "Check how well a PDF works with screen readers, get plain fixes, and fix the basics automatically."
    category = Category.OPTIMIZE
    accepts = PDF
    max_files = 1
    produces_pdf = False

    class Options(ToolOptions):
        fix_basics: bool = Field(
            False, description="Also return a copy with title, language and display settings fixed"
        )
        language: str = Field("en", max_length=20, description="Language code to set when fixing, e.g. en-GB, de, hi")

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        path = inputs[0]
        rows, facts = check(path)
        outputs: list[Path] = []
        fixed: list[str] = []
        if options.fix_basics:
            with open_pdf(path) as pdf:
                if not facts["title"]:
                    title = facts["first_line"] or stem(path).replace("-", " ").replace("_", " ")
                    pdf.docinfo["/Title"] = title
                    with pdf.open_metadata() as meta:
                        meta["dc:title"] = title
                    fixed.append(f"Set the title to “{title}”.")
                if not facts["lang"]:
                    pdf.Root.Lang = pikepdf.String(options.language)
                    fixed.append(f"Set the language to {options.language}.")
                prefs = pdf.Root.get("/ViewerPreferences")
                if prefs is None:
                    pdf.Root.ViewerPreferences = prefs = pdf.make_indirect(pikepdf.Dictionary())
                if not prefs.get("/DisplayDocTitle", False):
                    prefs.DisplayDocTitle = True
                    fixed.append("Readers now show the title instead of the file name.")
                for page in pdf.pages:
                    if "/Annots" in page and page.get("/Tabs") != "/S":
                        page.Tabs = pikepdf.Name.S
                        if "Set tab order to follow the document structure." not in fixed:
                            fixed.append("Set tab order to follow the document structure.")
                outputs.append(save_pdf(pdf, ctx.output_path(f"{stem(path)}-accessible.pdf")))
        out = ctx.output_path(f"{stem(path)}-accessibility.md")
        out.write_text(report(path.name, rows, fixed if options.fix_basics else None), encoding="utf-8")
        return [out, *outputs]
