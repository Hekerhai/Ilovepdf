"""Edit PDF, forms, digital signatures, split by text, rename and scan to PDF."""

import pdfplumber
import pikepdf
import pypdfium2 as pdfium
import pytest

from app.domain.errors import ValidationFailed
from app.tools.editor import describe_fields
from app.tools.overlay import user_rect
from app.tools.signatures import signature_report
from tests.conftest import data_url_png, make_image
from tests.test_tools import pages, run


def dark_fraction(path, page_index, box):
    """Share of dark pixels inside a box (fractions of the rendered, rotation-applied page)."""
    doc = pdfium.PdfDocument(path)
    image = doc[page_index].render(scale=1).to_pil().convert("L")
    w, h = image.size
    x0, y0, x1, y1 = (int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h))
    pixels = list(image.crop((x0, y0, x1, y1)).getdata())
    doc.close()
    return sum(1 for p in pixels if p < 80) / max(1, len(pixels))


def test_edit_pdf_draws_every_object_type(tmp_path, pdf3):
    objects = [
        {"type": "text", "page": 1, "x": 0.5, "y": 0.5, "text": "Added line one\nline two", "font_size": 18},
        {"type": "text", "page": 2, "x": 0.1, "y": 0.9, "text": "Unicode ÄΩ ✓", "font": "serif", "bold": True},
        {"type": "rect", "page": 1, "x": 0.1, "y": 0.1, "width": 0.2, "height": 0.1, "fill": "#000000"},
        {"type": "ellipse", "page": 1, "x": 0.4, "y": 0.1, "width": 0.2, "height": 0.1},
        {"type": "line", "page": 1, "x": 0.1, "y": 0.3, "x2": 0.9, "y2": 0.3},
        {"type": "arrow", "page": 1, "x": 0.1, "y": 0.35, "x2": 0.5, "y2": 0.45, "color": "#dc2626"},
        {"type": "highlight", "page": 1, "x": 0.1, "y": 0.6, "width": 0.3, "height": 0.03},
        {"type": "whiteout", "page": 3, "x": 0, "y": 0, "width": 1, "height": 0.25},
        {"type": "draw", "page": 1, "x": 0, "y": 0, "points": [[0.2, 0.7], [0.3, 0.75], [0.4, 0.7]]},
        {"type": "image", "page": 2, "x": 0.5, "y": 0.5, "width": 0.2, "height": 0.1, "image": data_url_png()},
    ]
    [edited] = run("edit_pdf", [pdf3], tmp_path, objects=objects)
    assert pages(edited) == 3
    with pdfplumber.open(edited) as doc:
        first = doc.pages[0]
        assert "Added line one" in first.extract_text() and "line two" in first.extract_text()
        word = next(w for w in first.extract_words() if w["text"] == "Added")
        assert abs(word["x0"] / first.width - 0.5) < 0.01
        assert 0.5 < word["top"] / first.height < 0.53
        assert "ÄΩ" in doc.pages[1].extract_text()
    assert dark_fraction(edited, 0, (0.12, 0.12, 0.28, 0.18)) > 0.95  # the filled black box
    assert dark_fraction(edited, 2, (0.05, 0.05, 0.6, 0.2)) == 0  # heading on page 3 whited out


@pytest.mark.parametrize("angle", [90, 180, 270])
def test_edit_pdf_and_form_fields_land_where_the_reader_sees_them(tmp_path, pdf3, angle):
    [rotated] = run("rotate", [pdf3], tmp_path, angle=angle)
    box = {"x": 0.1, "y": 0.1, "width": 0.25, "height": 0.1}
    [edited] = run("edit_pdf", [rotated], tmp_path, objects=[{"type": "rect", "page": 1, "fill": "#000000", **box}])
    assert dark_fraction(edited, 0, (0.12, 0.12, 0.33, 0.18)) > 0.95
    elsewhere = (0.5, 0.4, 0.95, 0.95)
    assert dark_fraction(edited, 0, elsewhere) == dark_fraction(rotated, 0, elsewhere)
    # Form widgets are placed in user space, so they go through visual_to_user; they must match the drawn box.
    with pikepdf.open(edited) as pdf:
        expected = user_rect(pdf.pages[0], **box)
    [form] = run("create_forms", [rotated], tmp_path, fields=[{"type": "text", "name": "f", "page": 1, **box}])
    with pikepdf.open(form) as pdf:
        assert [round(float(v)) for v in pdf.pages[0].Annots[0].Rect] == [round(v) for v in expected]


def test_create_then_fill_forms(tmp_path, pdf3):
    fields = [
        {"type": "text", "name": "full_name", "page": 1, "x": 0.1, "y": 0.3, "width": 0.4, "height": 0.04,
         "required": True},
        {"type": "multiline", "name": "notes", "page": 1, "x": 0.1, "y": 0.4, "width": 0.6, "height": 0.1},
        {"type": "checkbox", "name": "agree", "page": 1, "x": 0.1, "y": 0.55, "width": 0.03, "height": 0.02},
        {"type": "dropdown", "name": "plan", "page": 2, "x": 0.1, "y": 0.3, "width": 0.3, "height": 0.04,
         "options": ["Free", "Pro"], "default": "Free"},
        {"type": "radio", "name": "size", "page": 2, "x": 0.1, "y": 0.4, "width": 0.3, "height": 0.09,
         "options": ["Small", "Large"]},
        {"type": "signature", "name": "sign_here", "page": 3, "x": 0.5, "y": 0.8, "width": 0.3, "height": 0.08},
    ]  # fmt: skip
    [form] = run("create_forms", [pdf3], tmp_path, fields=fields)
    described = {f["name"]: f for f in describe_fields(form)}
    assert set(described) == {f["name"] for f in fields}
    assert described["size"]["options"] == ["Small", "Large"]
    assert described["plan"]["options"] == ["Free", "Pro"]
    with pdfplumber.open(form) as doc:
        assert "Small" in doc.pages[1].extract_text()  # radio labels are printed

    with pytest.raises(ValidationFailed):
        run("create_forms", [form], tmp_path, fields=[{**fields[0]}])  # duplicate name

    values = {"full_name": "Ada Lovelace", "notes": "Line 1\nLine 2", "agree": True, "plan": "Pro", "size": "Large"}
    [filled] = run("fill_forms", [form], tmp_path, fields=values)
    with pikepdf.open(filled) as pdf:
        form_ = pikepdf.form.Form(pdf)
        assert form_["full_name"].value == "Ada Lovelace"
        assert form_["agree"].checked is True
        assert str(form_["plan"].value) == "Pro"
        assert str(form_["size"].value) == "/Large"
    with pytest.raises(ValidationFailed):
        run("fill_forms", [form], tmp_path, fields={"nope": "x"})

    [flat] = run("fill_forms", [form], tmp_path, fields={"full_name": "Grace Hopper"}, flatten=True)
    with pdfplumber.open(flat) as doc:
        assert "Grace Hopper" in doc.pages[0].extract_text()


def test_digital_signature_sign_verify_and_tamper(tmp_path, pdf3):
    [signed] = run(
        "digital_sign", [pdf3], tmp_path, signer_name="Ada Lovelace", signer_email="ada@example.com",
        reason="Approved", page=99, position="bottom-left",
    )  # fmt: skip
    report = signature_report(signed)
    assert "Ada Lovelace" in report and "valid, document unchanged" in report and "self-signed" in report
    [md] = run("verify_signatures", [signed], tmp_path)
    assert md.suffix == ".md"

    # Change one byte inside the signed range (a comment, so the file still opens): the report must call it out.
    data = bytearray(signed.read_bytes())
    i = data.index(b"ReportLab Generated")
    data[i : i + 9] = b"ReportLaX"
    tampered = tmp_path / "tampered.pdf"
    tampered.write_bytes(bytes(data))
    assert "INVALID" in signature_report(tampered)

    assert "no digital signatures" in signature_report(pdf3)


def test_digital_signature_with_own_certificate_into_existing_field(tmp_path, pdf3):
    import base64

    from cryptography.hazmat.primitives.serialization import BestAvailableEncryption, pkcs12

    from app.tools.signatures import self_signed_pkcs12

    key, cert, _ = pkcs12.load_key_and_certificates(self_signed_pkcs12("Grace Hopper", None), None)
    p12 = pkcs12.serialize_key_and_certificates(b"grace", key, cert, None, BestAvailableEncryption(b"pw"))
    cert_url = "data:application/x-pkcs12;base64," + base64.b64encode(p12).decode()
    field = {"type": "signature", "name": "approver", "page": 1, "x": 0.5, "y": 0.8, "width": 0.3, "height": 0.08}
    [form] = run("create_forms", [pdf3], tmp_path, fields=[field])
    [signed] = run(
        "digital_sign", [form], tmp_path, certificate=cert_url, certificate_password="pw", field_name="approver"
    )
    report = signature_report(signed)
    assert "approver" in report and "Grace Hopper" in report
    with pytest.raises(ValidationFailed):
        run("digital_sign", [pdf3], tmp_path, certificate=cert_url, certificate_password="wrong")


def test_split_by_text(tmp_path, pdf3):
    parts = run("split_by_text", [pdf3], tmp_path, text="heading 2")
    assert [pages(p) for p in parts] == [1, 2]
    assert parts[1].name == "doc-002-Heading-2.pdf"
    after = run("split_by_text", [pdf3], tmp_path, text=r"Heading [12]", regex=True, split="after")
    assert [pages(p) for p in after] == [1, 1, 1]
    with pytest.raises(ValidationFailed):
        run("split_by_text", [pdf3], tmp_path, text="not in there")


def test_rename(tmp_path, pdf3, pdf2):
    with pikepdf.open(pdf3, allow_overwriting_input=True) as pdf:
        pdf.docinfo["/Title"] = "Quarterly report"
        pdf.save(pdf3)
    renamed = run("rename", [pdf3, pdf2], tmp_path, pattern="{n}-{title}{first_line}", start_at=7)
    assert [p.name for p in renamed] == ["7-Quarterly-reportHeading-1.pdf", "8-Heading-1.pdf"]
    with pytest.raises(ValidationFailed):
        run("rename", [pdf2], tmp_path, pattern="{nope}")


@pytest.mark.parametrize("mode", ["color", "grayscale", "enhanced", "black_white"])
def test_scan_to_pdf(tmp_path, mode):
    photo = make_image(tmp_path / "photo.jpg", size=(900, 1200), color=(180, 170, 150))
    [pdf] = run("scan_to_pdf", [photo, photo], tmp_path, filter=mode)
    with pikepdf.open(pdf) as doc:
        assert len(doc.pages) == 2
        assert round(float(doc.pages[0].mediabox[2])) == 595  # A4 by default


def test_new_tools_are_in_the_catalog():
    from app.tools.registry import default_registry

    ids = {t.id for t in default_registry().all()}
    assert {"edit_pdf", "fill_forms", "create_forms", "digital_sign", "verify_signatures"} <= ids
    assert {"split_by_text", "rename", "scan_to_pdf"} <= ids


def test_fill_a_form_made_in_the_browser(tmp_path):
    """pdf-lib names radio states 0, 1... and keeps the labels in /Opt; the server must accept the labels."""
    from pathlib import Path

    form = Path(__file__).parent / "fixtures" / "pdflib-form-rotated.pdf"  # made by the web app's create_forms
    assert [f.get("options") for f in describe_fields(form)] == [None, None, ["Free", "Pro"], ["Small", "Large"]]
    [filled] = run("fill_forms", [form], tmp_path, fields={"size": "Large", "plan": "Pro", "full_name": "Zoë Ω"})
    with pikepdf.open(filled) as pdf:
        f = pikepdf.form.Form(pdf)
        assert (str(f["size"].value), str(f["plan"].value), str(f["full_name"].value)) == ("/1", "Pro", "Zoë Ω")


@pytest.mark.parametrize("angle", [0, 90, 270])
def test_annotations_land_where_the_reader_sees_them(tmp_path, pdf3, angle):
    import pymupdf

    [rotated] = run("rotate", [pdf3], tmp_path, angle=angle) if angle else [pdf3]
    box = {"x": 0.1, "y": 0.1, "width": 0.25, "height": 0.1}
    objects = [
        {"type": "rect", "page": 1, "fill": "#000000", "color": "#000000", "comment": "Check this", **box},
        {"type": "note", "page": 1, "x": 0.8, "y": 0.8, "text": "Looks good"},
        {"type": "highlight", "page": 2, "x": 0.1, "y": 0.1, "width": 0.4, "height": 0.03},
        {"type": "underline", "page": 2, "x": 0.1, "y": 0.2, "width": 0.4, "height": 0.03},
        {"type": "strikeout", "page": 2, "x": 0.1, "y": 0.3, "width": 0.4, "height": 0.03},
        {"type": "text", "page": 2, "x": 0.1, "y": 0.5, "text": "Free text"},
        {"type": "arrow", "page": 3, "x": 0.1, "y": 0.1, "x2": 0.5, "y2": 0.5},
        {"type": "ellipse", "page": 3, "x": 0.5, "y": 0.6, "width": 0.2, "height": 0.1},
        {"type": "draw", "page": 3, "x": 0, "y": 0, "points": [[0.1, 0.8], [0.2, 0.85], [0.3, 0.8]]},
    ]
    [out] = run("annotate_pdf", [rotated], tmp_path, objects=objects, author="Ada")
    assert dark_fraction(out, 0, (0.12, 0.12, 0.33, 0.18)) > 0.9
    elsewhere = (0.4, 0.3, 0.7, 0.7)
    assert dark_fraction(out, 0, elsewhere) == dark_fraction(rotated, 0, elsewhere)
    doc = pymupdf.open(out)
    kinds = [[a.type[1] for a in page.annots()] for page in doc]
    assert kinds == [["Square", "Text"], ["Highlight", "Underline", "StrikeOut", "FreeText"], ["Line", "Circle", "Ink"]]
    first = next(doc[0].annots())
    assert first.info["content"] == "Check this" and first.info["title"] == "Ada"
    assert "Free text" in doc[1].get_text() or any(a.info["content"] == "Free text" for a in doc[1].annots())


def test_accessibility_check_and_fix(tmp_path, pdf3):
    import zipfile

    [report] = run("accessibility_check", [pdf3], tmp_path)
    text = report.read_text()
    assert "| Document title | Fails |" in text and "| Language | Fails |" in text and "| Tags" in text
    outputs = run("accessibility_check", [pdf3], tmp_path, fix_basics=True, language="en-GB")
    fixed_pdf = next(p for p in outputs if p.suffix == ".pdf")
    with pikepdf.open(fixed_pdf) as pdf:
        assert str(pdf.Root.Lang) == "en-GB" and str(pdf.docinfo.Title) == "Heading 1"
        assert pdf.Root.ViewerPreferences.DisplayDocTitle
    [again] = run("accessibility_check", [fixed_pdf], tmp_path)
    assert "| Document title | Pass |" in again.read_text() and "| Language | Pass |" in again.read_text()
    assert zipfile  # (multi-output tasks are zipped by the job service)


def test_ebook_and_zip_to_pdf(tmp_path, pdf3, pdf2):
    import zipfile

    import pymupdf

    from tests.conftest import make_image

    # A tiny EPUB built by hand: mimetype, container, package, one chapter.
    epub = tmp_path / "book.epub"
    with zipfile.ZipFile(epub, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container version="1.0" '
            'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile '
            'full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        z.writestr(
            "OEBPS/content.opf",
            '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" '
            'version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<dc:identifier id="id">x</dc:identifier><dc:title>Tiny Book</dc:title><dc:language>en</dc:language>'
            '</metadata><manifest><item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/></manifest>'
            '<spine><itemref idref="c1"/></spine></package>',
        )
        z.writestr("OEBPS/c1.xhtml", '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><head>'
                   "<title>One</title></head><body><h1>Chapter one</h1>" + "<p>It was a quiet morning.</p>" * 200
                   + "</body></html>")  # fmt: skip
    [book] = run("ebook_to_pdf", [epub], tmp_path, page_size="A5")
    doc = pymupdf.open(book)
    assert doc.page_count >= 2 and "Chapter one" in doc[0].get_text()
    assert round(doc[0].rect.width) == 420  # A5

    bundle = tmp_path / "bundle.zip"
    with zipfile.ZipFile(bundle, "w") as z:
        z.write(pdf3, "a/first.pdf")
        z.write(make_image(tmp_path / "photo.png"), "b/photo.png")
        z.write(epub, "c/book.epub")
        z.writestr("../../evil.pdf", b"%PDF-1.4 not really")  # path tricks are ignored; it's just unreadable
        z.writestr("notes.xyz", b"unknown type")
    [merged] = run("zip_to_pdf", [bundle], tmp_path)
    with pikepdf.open(merged) as pdf:
        titles = [item.title for item in pdf.open_outline().root]
    assert titles[:3] == ["first", "photo", "book"] and titles[-1] == "Files not included"
    assert not (tmp_path.parent / "evil.pdf").exists()
