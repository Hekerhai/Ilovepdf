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
