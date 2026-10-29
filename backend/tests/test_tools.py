"""Every tool runs end to end against real files (no mocks for the PDF engines)."""

import shutil
from pathlib import Path

import pikepdf
import pytest

from app.domain.errors import ServiceUnavailable, ValidationFailed
from app.engines.converters import LibreOfficeConverter
from app.tools.base import ToolContext
from app.tools.pages import parse_page_list
from app.tools.registry import default_registry
from tests.conftest import data_url_png, make_image, make_pdf

REG = default_registry()


def run(tool_id: str, inputs: list[Path], tmp_path: Path, **options):
    tool = REG.get(tool_id)
    ctx = ToolContext(work_dir=tmp_path / f"work-{tool_id}", converter=LibreOfficeConverter())
    ctx.work_dir.mkdir(parents=True, exist_ok=True)
    outputs = tool.run(inputs, tool.Options(**options), ctx)
    assert outputs and all(p.exists() and p.stat().st_size > 0 for p in outputs)
    return outputs


def pages(path: Path) -> int:
    with pikepdf.open(path) as pdf:
        return len(pdf.pages)


def text(path: Path) -> str:
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def test_page_ranges():
    assert parse_page_list("1-3,5", 6) == [0, 1, 2, 4]
    assert parse_page_list("4-", 5) == [3, 4]
    assert parse_page_list("odd", 5) == [0, 2, 4]
    assert parse_page_list("3-1", 3) == [2, 1, 0]
    assert parse_page_list("last", 7) == [6]
    with pytest.raises(ValidationFailed):
        parse_page_list("9", 3)


def test_merge(tmp_path, pdf3, pdf2):
    [out] = run("merge", [pdf3, pdf2], tmp_path)
    assert pages(out) == 5
    with pikepdf.open(out) as pdf, pdf.open_outline() as outline:
        assert [i.title for i in outline.root] == ["doc", "other"]


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({"mode": "ranges", "ranges": "1-2, 3"}, [2, 1]),
        ({"mode": "every", "every": 2}, [2, 1]),
        ({"mode": "all"}, [1, 1, 1]),
        ({"mode": "ranges", "ranges": "1,3", "merge_output": True}, [2]),
        ({"mode": "size", "max_size_mb": 0.001}, [1, 1, 1]),
    ],
)
def test_split(tmp_path, pdf3, options, expected):
    assert [pages(p) for p in run("split", [pdf3], tmp_path, **options)] == expected


def test_split_by_bookmarks(tmp_path, pdf3, pdf2):
    [merged] = run("merge", [pdf3, pdf2], tmp_path)
    assert [pages(p) for p in run("split", [merged], tmp_path, mode="bookmarks")] == [3, 2]


def test_split_in_half(tmp_path, pdf3):
    [out] = run("split_in_half", [pdf3], tmp_path)
    assert pages(out) == 6


def test_remove_extract_organize(tmp_path, pdf3, pdf2):
    [removed] = run("remove_pages", [pdf3], tmp_path, pages="2")
    assert pages(removed) == 2 and "Hello page 2" not in text(removed)
    [extracted] = run("extract_pages", [pdf3], tmp_path, pages="3,1")
    assert text(extracted).index("page 3") < text(extracted).index("page 1")
    [organized] = run(
        "organize",
        [pdf3, pdf2],
        tmp_path,
        pages=[{"file": 1, "page": 2}, {"file": 0, "page": 1, "rotate": 90}, {"file": 0}],
    )
    assert pages(organized) == 3
    with pikepdf.open(organized) as pdf:
        assert int(pdf.pages[1].obj.get("/Rotate", 0)) == 90
    with pytest.raises(ValidationFailed):
        run("remove_pages", [pdf3], tmp_path, pages="1-3")


def test_rotate_flip_mix_nup_resize(tmp_path, pdf3, pdf2):
    [rotated] = run("rotate", [pdf3], tmp_path, angle=180, pages="2")
    with pikepdf.open(rotated) as pdf:
        assert [int(p.obj.get("/Rotate", 0)) for p in pdf.pages] == [0, 180, 0]
    run("flip", [pdf3], tmp_path)
    [mixed] = run("alternate_mix", [pdf3, pdf2], tmp_path, reverse_last=True)
    assert pages(mixed) == 5
    assert text(mixed).index("Hello page 1") < text(mixed).index("Other text 2") < text(mixed).index("Hello page 2")
    [nup] = run("n_up", [pdf3], tmp_path, per_sheet=2)
    assert pages(nup) == 2
    [resized] = run("resize", [pdf3], tmp_path, size="Letter")
    with pikepdf.open(resized) as pdf:
        assert [round(float(v)) for v in pdf.pages[0].mediabox] == [0, 0, 612, 792]


def test_compress_repair_grayscale(tmp_path, pdf3):
    [compressed] = run("compress", [pdf3], tmp_path, level="extreme")
    assert compressed.stat().st_size <= pdf3.stat().st_size
    broken = tmp_path / "broken.pdf"
    data = pdf3.read_bytes()
    broken.write_bytes(data[: data.rfind(b"xref")])  # chop the xref table
    [repaired] = run("repair", [broken], tmp_path)
    assert pages(repaired) == 3
    [gray] = run("grayscale", [pdf3], tmp_path)
    assert pages(gray) == 3


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")
def test_ocr(tmp_path, pdf3):
    [jpg, *_] = run("pdf_to_images", [pdf3], tmp_path, dpi=150, pages="1")
    [scanned] = run("images_to_pdf", [jpg], tmp_path)
    assert "Hello" not in text(scanned)
    [ocred] = run("ocr", [scanned], tmp_path, languages=["eng"])
    assert "Hello" in text(ocred) and "Heading 1" in text(ocred)


def test_images_to_pdf(tmp_path):
    imgs = [
        make_image(tmp_path / "a.jpg"),
        make_image(tmp_path / "b.png", mode="RGBA", color=(0, 0, 255)),
        make_image(tmp_path / "c.webp", size=(300, 600)),
    ]
    [one] = run("images_to_pdf", imgs, tmp_path, page_size="A4", margin_mm=10)
    assert pages(one) == 3
    assert len(run("images_to_pdf", imgs, tmp_path, single_file=False)) == 3


@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice not installed")
def test_office_and_html_to_pdf(tmp_path):
    from docx import Document  # bundled with pdf2docx

    doc = Document()
    doc.add_heading("Quarterly report", 0)
    doc.add_paragraph("Revenue grew.")
    docx = tmp_path / "report.docx"
    doc.save(docx)
    [pdf] = run("word_to_pdf", [docx], tmp_path)
    assert "Quarterly report" in text(pdf)
    page = tmp_path / "page.html"
    page.write_text("<h1>Hello HTML</h1><p>From a file</p>")
    [html_pdf] = run("html_to_pdf", [page], tmp_path)
    assert "Hello HTML" in text(html_pdf)


def test_convert_from_pdf(tmp_path, pdf3):
    assert len(run("pdf_to_images", [pdf3], tmp_path, format="png", dpi=72)) == 3
    [docx] = run("pdf_to_word", [pdf3], tmp_path)
    assert docx.suffix == ".docx"
    [pptx] = run("pdf_to_powerpoint", [pdf3], tmp_path)
    from pptx import Presentation

    assert len(Presentation(pptx).slides) == 3
    [xlsx] = run("pdf_to_excel", [pdf3], tmp_path)
    from openpyxl import load_workbook

    assert load_workbook(xlsx).sheetnames == ["Page 1", "Page 2", "Page 3"]
    [txt] = run("pdf_to_text", [pdf3], tmp_path)
    assert "Hello page 2" in txt.read_text()
    [md] = run("pdf_to_markdown", [pdf3], tmp_path)
    assert "# Heading 1" in md.read_text()
    [pdfa] = run("pdf_to_pdfa", [pdf3], tmp_path)
    with pikepdf.open(pdfa) as pdf:
        assert "pdfaid" in str(pdf.open_metadata())


def test_extract_images(tmp_path):
    img = make_image(tmp_path / "pic.png", size=(120, 90))
    [pdf] = run("images_to_pdf", [img], tmp_path)
    assert len(run("extract_images", [pdf], tmp_path)) == 1
    with pytest.raises(ValidationFailed):
        run("extract_images", [make_pdf(tmp_path / "plain.pdf", 1)], tmp_path)


def test_stamping_tools(tmp_path, pdf3):
    [wm] = run("watermark", [pdf3], tmp_path, text="DRAFT ÄÖ", rotation=0, tiled=True)
    assert "DRAFT ÄÖ" in text(wm)
    run("watermark", [pdf3], tmp_path, text=None, image=data_url_png(), pages="1")
    [numbered] = run("page_numbers", [pdf3], tmp_path, template="Page {page} of {total}", skip_first=True)
    body = text(numbered)
    assert "Page 1 of 2" in body and "Page 2 of 2" in body and "Page 3" not in body
    [hf] = run("header_footer", [pdf3], tmp_path, header_left="ACME {filename}")
    assert "ACME doc" in text(hf) and "3 / 3" in text(hf)
    outs = run("bates", [pdf3, pdf3], tmp_path, prefix="X-", digits=4)
    assert "X-0001" in text(outs[0]) and "X-0004" in text(outs[1])


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")
@pytest.mark.parametrize("angle", [90, 180, 270])
def test_stamp_reads_upright_on_rotated_pages(tmp_path, pdf3, angle):
    import subprocess

    [rotated] = run("rotate", [pdf3], tmp_path, angle=angle)
    [numbered] = run("page_numbers", [rotated], tmp_path, template="STAMPED {page}", font_size=28)
    # Render as a viewer would (rotation applied), then OCR: the stamp must read left-to-right.
    [png] = run("pdf_to_images", [numbered], tmp_path, format="png", dpi=100, pages="1")
    ocr = subprocess.run(["tesseract", str(png), "-", "--psm", "11"], capture_output=True, text=True).stdout
    assert "STAMPED" in ocr


def test_crop_metadata_bookmarks_annotations_flatten(tmp_path, pdf3):
    [cropped] = run("crop", [pdf3], tmp_path, top_mm=20, left_mm=5, right_mm=5, bottom_mm=5)
    with pikepdf.open(cropped) as pdf:
        assert float(pdf.pages[0].cropbox[3]) < float(pdf.pages[0].mediabox[3])
    [meta] = run("edit_metadata", [pdf3], tmp_path, title="New title", remove_all=True)
    with pikepdf.open(meta) as pdf:
        assert str(pdf.docinfo["/Title"]) == "New title" and "/Producer" not in pdf.docinfo
    [marked] = run(
        "create_bookmarks",
        [pdf3],
        tmp_path,
        bookmarks=[{"title": "Intro", "page": 1}, {"title": "Detail", "page": 2, "level": 1}],
    )
    with pikepdf.open(marked) as pdf, pdf.open_outline() as outline:
        assert outline.root[0].title == "Intro" and outline.root[0].children[0].title == "Detail"
    run("delete_annotations", [pdf3], tmp_path)
    run("flatten", [pdf3], tmp_path)


def test_sign(tmp_path, pdf3):
    [signed] = run(
        "sign",
        [pdf3],
        tmp_path,
        signature=data_url_png(),
        placements=[{"page": 3, "x": 0.6, "y": 0.8, "width": 0.25}],
        add_date=True,
    )
    import pdfplumber

    with pdfplumber.open(signed) as pdf:
        assert len(pdf.pages[2].images) == 1 and len(pdf.pages[0].images) == 0


def test_protect_and_unlock(tmp_path, pdf3):
    [locked] = run("protect", [pdf3], tmp_path, password="s3cret", allow_copy=False)
    with pytest.raises(pikepdf.PasswordError):
        pikepdf.open(locked)
    with pytest.raises(ValidationFailed):
        run("merge", [locked, pdf3], tmp_path)
    with pytest.raises(ValidationFailed):
        run("unlock", [locked], tmp_path, password="wrong")
    [unlocked] = run("unlock", [locked], tmp_path, password="s3cret")
    with pikepdf.open(unlocked) as pdf:
        assert not pdf.is_encrypted


def test_compare(tmp_path, pdf3):
    changed = make_pdf(tmp_path / "v2.pdf", 3, text="Hello changed")
    [report] = run("compare", [pdf3, changed], tmp_path)
    body = report.read_text()
    assert "+3 lines added" in body and "−3 lines removed" in body


def test_ai_tools_need_a_provider(tmp_path, pdf3):
    with pytest.raises(ServiceUnavailable):
        run("ai_summarize", [pdf3], tmp_path)


def test_ai_tools_with_fake_provider(tmp_path, pdf3):
    class Fake:
        available = True

        def complete(self, *, system, prompt, max_tokens=2048):
            assert "Hello page 1" in prompt
            return "- summary"

    tool = REG.get("ai_summarize")
    ctx = ToolContext(work_dir=tmp_path, ai=Fake())
    [out] = tool.run([pdf3], tool.Options(), ctx)
    assert out.read_text() == "- summary"


def test_every_tool_describes_itself():
    for tool in REG.all():
        info = tool.describe()
        assert info["options_schema"]["type"] == "object", tool.id


def test_redact_removes_text(tmp_path):
    src = make_pdf(tmp_path / "secret.pdf", 2, text="Contact jane@example.com about page")
    [out] = run(
        "redact",
        [src],
        tmp_path,
        terms=["Heading"],
        patterns=["email"],
        areas=[{"page": 2, "x": 0, "y": 0.9, "width": 1, "height": 0.1}],
    )
    body = text(out)
    assert "jane@example.com" not in body and "Heading" not in body and "Contact" in body


def test_web_catalog_snapshot_is_current():
    """The web app ships a snapshot of the catalog; regenerate it with `python -m app.tools.export`."""
    import json

    from app.tools.export import catalog

    snapshot = Path(__file__).parents[2] / "frontend" / "src" / "lib" / "tools.generated.json"
    if not snapshot.exists():
        pytest.skip("frontend not present")
    assert json.loads(snapshot.read_text()) == json.loads(json.dumps(catalog())), "run: python -m app.tools.export"
