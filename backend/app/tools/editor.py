"""Edit PDF (text, images, shapes, drawing), fill forms and create forms.

The web app runs all three on the device with pdf-lib; these server versions back the API, workflows and the
cases the browser can't handle (for example non-Latin text). Positions are fractions of the visible page with the
origin at the top-left, exactly as the editor shows it.
"""

import math
from pathlib import Path
from typing import Literal

import pikepdf
import pikepdf.form
from pydantic import BaseModel, ConfigDict, Field, model_validator
from reportlab.pdfgen.canvas import Canvas

from app.domain.errors import ValidationFailed
from app.tools.base import Category, Tool, ToolContext, ToolOptions, stem
from app.tools.edit import text_font
from app.tools.overlay import color, decode_image, page_rotation, stamp_pages, user_rect, visual_size
from app.tools.pdfio import open_pdf, save_pdf
from app.tools.registry import register

ObjectType = Literal["text", "image", "rect", "ellipse", "line", "arrow", "highlight", "whiteout", "draw"]

# ReportLab's built-in fonts, by family then (bold, italic).
STANDARD_FONTS = {
    "sans": {(False, False): "Helvetica", (True, False): "Helvetica-Bold", (False, True): "Helvetica-Oblique",
             (True, True): "Helvetica-BoldOblique"},
    "serif": {(False, False): "Times-Roman", (True, False): "Times-Bold", (False, True): "Times-Italic",
              (True, True): "Times-BoldItalic"},
    "mono": {(False, False): "Courier", (True, False): "Courier-Bold", (False, True): "Courier-Oblique",
             (True, True): "Courier-BoldOblique"},
}  # fmt: skip

# Shared with the editor: the first baseline sits ASCENT * size below the top of a text box, lines LINE_HEIGHT apart.
ASCENT = 0.8
LINE_HEIGHT = 1.2


class EditObject(BaseModel):
    """One thing to add to a page. x/y/width/height are fractions of the visible page, origin top-left."""

    model_config = ConfigDict(extra="forbid")

    type: ObjectType
    page: int = Field(..., ge=1)
    x: float = Field(..., ge=-1, le=2)
    y: float = Field(..., ge=-1, le=2)
    width: float = Field(0, ge=0, le=2)
    height: float = Field(0, ge=0, le=2)
    x2: float | None = Field(None, description="Line and arrow end point")
    y2: float | None = None
    points: list[tuple[float, float]] | None = Field(None, description="Freehand drawing path")
    text: str | None = None
    font: Literal["sans", "serif", "mono"] = "sans"
    font_size: float = Field(14, gt=1, le=400, description="Points")
    bold: bool = False
    italic: bool = False
    color: str = "#111827"
    fill: str | None = None
    stroke_width: float = Field(2, ge=0, le=50)
    opacity: float = Field(1, ge=0, le=1)
    image: str | None = Field(None, description="Image as a data URL")

    @model_validator(mode="after")
    def _check(self):
        if self.type == "text" and not (self.text or "").strip():
            raise ValueError("Text objects need some text.")
        if self.type == "image" and not self.image:
            raise ValueError("Image objects need an image.")
        if self.type in ("line", "arrow") and (self.x2 is None or self.y2 is None):
            raise ValueError("Lines need an end point (x2, y2).")
        if self.type == "draw" and not self.points:
            raise ValueError("Drawings need points.")
        if self.type in ("image", "rect", "ellipse", "highlight", "whiteout") and (self.width <= 0 or self.height <= 0):
            raise ValueError(f"A {self.type} needs a width and height.")
        return self


def _font_for(obj: EditObject) -> str:
    try:
        (obj.text or "").encode("latin-1")
    except UnicodeEncodeError:
        return text_font()  # built-in fonts are Latin-1 only
    return STANDARD_FONTS[obj.font][(obj.bold, obj.italic)]


def _draw_object(c: Canvas, obj: EditObject, w: float, h: float) -> None:
    def pt(fx: float, fy: float) -> tuple[float, float]:
        return fx * w, h - fy * h

    c.saveState()
    stroke = color(obj.color)
    c.setStrokeColor(stroke)
    c.setLineWidth(obj.stroke_width)
    c.setLineCap(1)
    c.setLineJoin(1)
    c.setStrokeAlpha(obj.opacity)
    c.setFillAlpha(obj.opacity)
    x, top = pt(obj.x, obj.y)
    bw, bh = obj.width * w, obj.height * h
    y = top - bh

    if obj.type == "text":
        c.setFillColor(stroke)
        c.setFont(_font_for(obj), obj.font_size)
        baseline = top - obj.font_size * ASCENT
        for i, line in enumerate((obj.text or "").split("\n")):
            c.drawString(x, baseline - i * obj.font_size * LINE_HEIGHT, line)
    elif obj.type == "image":
        c.drawImage(decode_image(obj.image or ""), x, y, bw, bh, mask="auto")
    elif obj.type in ("rect", "ellipse"):
        has_fill = obj.fill is not None
        if has_fill:
            c.setFillColor(color(obj.fill))
        draw_stroke = obj.stroke_width > 0
        if obj.type == "rect":
            c.rect(x, y, bw, bh, stroke=int(draw_stroke), fill=int(has_fill))
        else:
            c.ellipse(x, y, x + bw, y + bh, stroke=int(draw_stroke), fill=int(has_fill))
    elif obj.type in ("highlight", "whiteout"):
        fill = obj.fill or ("#FDE047" if obj.type == "highlight" else "#FFFFFF")
        c.setFillColor(color(fill))
        if obj.type == "highlight":
            c.setFillAlpha(min(obj.opacity, 0.4))
        c.rect(x, y, bw, bh, stroke=0, fill=1)
    elif obj.type in ("line", "arrow"):
        x2, y2 = pt(obj.x2 or 0, obj.y2 or 0)
        c.line(x, top, x2, y2)
        if obj.type == "arrow":
            head = max(8.0, obj.stroke_width * 4)
            angle = math.atan2(y2 - top, x2 - x)
            for side in (-1, 1):
                a = angle + math.pi - side * math.pi / 7
                c.line(x2, y2, x2 + head * math.cos(a), y2 + head * math.sin(a))
    elif obj.type == "draw":
        path = c.beginPath()
        for i, (fx, fy) in enumerate(obj.points or []):
            px, py = pt(fx, fy)
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        c.drawPath(path, stroke=1, fill=0)
    c.restoreState()


@register
class EditPdfTool(Tool):
    id = "edit_pdf"
    name = "Edit PDF"
    description = "Add text, images, shapes, highlights and freehand drawings, or white out content."
    category = Category.EDIT
    max_files = 1
    browser_capable = True

    class Options(ToolOptions):
        objects: list[EditObject] = Field(..., min_length=1, description="What to add, and where")
        flatten: bool = Field(False, description="Flatten form fields and annotations into the page")

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        by_page: dict[int, list[EditObject]] = {}
        for obj in options.objects:
            by_page.setdefault(obj.page - 1, []).append(obj)
        with open_pdf(inputs[0]) as pdf:
            if max(by_page) >= len(pdf.pages):
                raise ValidationFailed(f"Page {max(by_page) + 1} doesn't exist; this PDF has {len(pdf.pages)}.")

            def draw(c: Canvas, index: int, w: float, h: float) -> None:
                for obj in by_page[index]:
                    _draw_object(c, obj, w, h)

            stamp_pages(pdf, draw, set(by_page))
            if options.flatten:
                pdf.flatten_annotations(mode="all")
            return [save_pdf(pdf, ctx.output_path(f"{stem(inputs[0])}-edited.pdf"))]


# ---- Fill forms ------------------------------------------------------------------------------------------------


def describe_fields(path: Path) -> list[dict]:
    """The fillable fields of a PDF, for the API (the web app reads them with pdf-lib instead)."""
    f = pikepdf.form
    kinds = {f.TextField: "text", f.CheckboxField: "checkbox", f.ChoiceField: "dropdown", f.RadioButtonGroup: "radio"}
    with open_pdf(path) as pdf:
        names = [name for name, _ in f.Form(pdf).items()]
        form = f.Form(pdf)  # listing leaves stale wrappers behind in pikepdf, so look fields up in a fresh Form
        out = []
        for name in names:
            field = form[name]
            entry: dict = {"name": name, "type": kinds.get(type(field), "other")}
            if isinstance(field, f.ChoiceField):
                entry["options"] = [str(o.display_value) for o in field.options]
            if isinstance(field, f.RadioButtonGroup):
                entry["options"] = [label for label, _ in _radio_choices(field)]
            out.append(entry)
        return out


def _radio_choices(group) -> list[tuple[str, object]]:
    """(label, option) pairs. Labels come from /Opt when present (pdf-lib names states 0, 1...), else state names."""
    labels = group._field.obj.get("/Opt")
    pairs = []
    for option in group.options:
        state = str(option.on_value).lstrip("/")
        if labels is not None and state.isdigit() and int(state) < len(labels):
            state = str(labels[int(state)])
        pairs.append((state, option))
    return pairs


@register
class FillFormsTool(Tool):
    id = "fill_forms"
    name = "Fill PDF forms"
    description = "Type into a PDF's form fields, tick its boxes and pick its options, then save or flatten it."
    category = Category.EDIT
    max_files = 1
    browser_capable = True

    class Options(ToolOptions):
        fields: dict[str, str | bool] = Field(
            ..., description="Field name to value: text, true/false for checkboxes, or the option to pick"
        )
        flatten: bool = Field(False, description="Flatten so the answers can't be changed")

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        with open_pdf(inputs[0]) as pdf:
            # Listing leaves stale wrappers behind in pikepdf, so list with one Form and fill through a fresh one.
            names = {name for name, _ in pikepdf.form.Form(pdf).items()}
            form = _form(pdf)
            if not names:
                raise ValidationFailed("This PDF has no fillable fields. Use Create forms to add some.")
            unknown = sorted(set(options.fields) - names)
            if unknown:
                raise ValidationFailed(f"No field named {', '.join(repr(u) for u in unknown[:5])} in this PDF.")
            for name, value in options.fields.items():
                _fill(pdf, form, name, value)
            if options.flatten:
                # qpdf won't flatten fields while NeedAppearances is set; this draws the rest and clears it.
                pdf.generate_appearance_streams()
                pdf.flatten_annotations(mode="all")
            return [save_pdf(pdf, ctx.output_path(f"{stem(inputs[0])}-filled.pdf"))]


def _form(pdf: pikepdf.Pdf) -> pikepdf.form.Form:
    """A form that draws field appearances, so the values show (and survive flattening) in every viewer."""
    fonts = pdf.Root.AcroForm.get("/DR", {}).get("/Font", {}) if "/AcroForm" in pdf.Root else {}
    for key in list(fonts.keys()):
        font = fonts[key]
        if font.get("/Subtype") == pikepdf.Name.Type1 and "/FontDescriptor" not in font:
            # The 14 standard fonts may omit a descriptor, but pikepdf's appearance generator needs one.
            font.FontDescriptor = pdf.make_indirect(
                pikepdf.Dictionary(
                    Type=pikepdf.Name.FontDescriptor, FontName=font.get("/BaseFont", pikepdf.Name.Helvetica),
                    Flags=32, FontBBox=[-166, -225, 1000, 931], ItalicAngle=0, Ascent=718, Descent=-207,
                    CapHeight=718, StemV=88,
                )
            )  # fmt: skip
    return pikepdf.form.Form(pdf, pikepdf.form.ExtendedAppearanceStreamGenerator)


def _fill(pdf: pikepdf.Pdf, form: pikepdf.form.Form, name: str, value: str | bool) -> None:
    try:
        _set_field(form[name], value)
    except ValidationFailed:
        raise
    except Exception:
        # Some fonts defeat the appearance generator: store the value and let the reader draw it.
        _set_field(pikepdf.form.Form(pdf)[name], value)
        pdf.Root.AcroForm.NeedAppearances = True


def _set_field(field, value: str | bool) -> None:
    f = pikepdf.form
    targets = field if isinstance(field, f.MultipleFieldProxy) else [field]
    for target in targets:
        if isinstance(target, f.CheckboxField):
            target.checked = value is True or str(value).lower() in ("true", "yes", "on", "1")
        elif isinstance(target, f.RadioButtonGroup):
            match = [option for label, option in _radio_choices(target) if label == str(value)]
            if not match:
                raise ValidationFailed(f"'{value}' is not one of the choices for this field.")
            match[0].select()
        elif isinstance(target, f.ChoiceField):
            target.value = str(value)
        elif isinstance(target, f.TextField):
            target.value = "" if value is False else str(value)


# ---- Create forms ----------------------------------------------------------------------------------------------

FieldType = Literal["text", "multiline", "checkbox", "dropdown", "radio", "signature"]


class FormFieldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: FieldType
    name: str = Field(..., min_length=1, max_length=120)
    page: int = Field(..., ge=1)
    x: float = Field(..., ge=0, le=1)
    y: float = Field(..., ge=0, le=1)
    width: float = Field(..., gt=0, le=1)
    height: float = Field(..., gt=0, le=1)
    options: list[str] = Field(default_factory=list, description="Choices for dropdowns and radio groups")
    required: bool = False
    default: str | None = None
    font_size: float = Field(0, ge=0, le=72, description="0 = auto size")

    @model_validator(mode="after")
    def _check(self):
        if self.type in ("dropdown", "radio") and not self.options:
            raise ValueError(f"'{self.name}' needs at least one option.")
        return self


FF_REQUIRED = 1 << 1
FF_MULTILINE = 1 << 12
FF_NO_TOGGLE_OFF = 1 << 14
FF_RADIO = 1 << 15
FF_COMBO = 1 << 17
WIDGET_PRINT = 4


def _ensure(container, key: str, default):
    """dict.setdefault for pikepdf dictionaries."""
    if key not in container:
        container[key] = default
    return container[key]


def _stream(pdf: pikepdf.Pdf, w: float, h: float, content: str) -> pikepdf.Stream:
    stream = pikepdf.Stream(pdf, content.encode())
    stream.Type = pikepdf.Name.XObject
    stream.Subtype = pikepdf.Name.Form
    stream.BBox = [0, 0, w, h]
    return stream


def _box(w: float, h: float) -> str:
    return f"q 1 g 0 0 {w:.2f} {h:.2f} re f 0.6 G 0.75 w 0.5 0.5 {w - 1:.2f} {h - 1:.2f} re S Q\n"


def _check_mark(w: float, h: float, round_: bool = False) -> str:
    if round_:
        r = min(w, h) * 0.25
        cx, cy, k = w / 2, h / 2, 0.5523 * min(w, h) * 0.25
        return (
            f"q 0 g {cx + r:.2f} {cy:.2f} m "
            f"{cx + r:.2f} {cy + k:.2f} {cx + k:.2f} {cy + r:.2f} {cx:.2f} {cy + r:.2f} c "
            f"{cx - k:.2f} {cy + r:.2f} {cx - r:.2f} {cy + k:.2f} {cx - r:.2f} {cy:.2f} c "
            f"{cx - r:.2f} {cy - k:.2f} {cx - k:.2f} {cy - r:.2f} {cx:.2f} {cy - r:.2f} c "
            f"{cx + k:.2f} {cy - r:.2f} {cx + r:.2f} {cy - k:.2f} {cx + r:.2f} {cy:.2f} c f Q\n"
        )
    lw = max(1.0, min(w, h) / 9)
    return (
        f"q 0 G {lw:.2f} w 1 J 1 j {w * 0.22:.2f} {h * 0.52:.2f} m {w * 0.42:.2f} {h * 0.28:.2f} l "
        f"{w * 0.78:.2f} {h * 0.74:.2f} l S Q\n"
    )


@register
class CreateFormsTool(Tool):
    id = "create_forms"
    name = "Create PDF forms"
    description = (
        "Turn any PDF into a fillable form with text boxes, checkboxes, dropdowns, radio buttons and signature fields."
    )
    category = Category.EDIT
    max_files = 1
    browser_capable = True

    class Options(ToolOptions):
        fields: list[FormFieldSpec] = Field(..., min_length=1)

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        names = [f.name for f in options.fields]
        if len(set(names)) != len(names):
            raise ValidationFailed("Each field needs a unique name.")
        with open_pdf(inputs[0]) as pdf:
            if "/AcroForm" not in pdf.Root:
                pdf.Root.AcroForm = pdf.make_indirect(pikepdf.Dictionary(Fields=pikepdf.Array()))
            acro = pdf.Root.AcroForm
            existing = {str(f.get("/T", "")) for f in acro.get("/Fields", [])}
            clash = sorted(set(names) & existing)
            if clash:
                raise ValidationFailed(f"This PDF already has a field named '{clash[0]}'.")
            _ensure(acro, "/Fields", pikepdf.Array())
            acro.DA = pikepdf.String("/Helv 0 Tf 0 g")
            resources = _ensure(acro, "/DR", pikepdf.Dictionary())
            fonts = _ensure(resources, "/Font", pikepdf.Dictionary())
            _ensure(
                fonts,
                "/Helv",
                pdf.make_indirect(
                    pikepdf.Dictionary(
                        Type=pikepdf.Name.Font,
                        Subtype=pikepdf.Name.Type1,
                        BaseFont=pikepdf.Name.Helvetica,
                        Encoding=pikepdf.Name.WinAnsiEncoding,
                    )
                ),
            )
            for spec in options.fields:
                if spec.page > len(pdf.pages):
                    raise ValidationFailed(f"Page {spec.page} doesn't exist; this PDF has {len(pdf.pages)}.")
                self._add(pdf, spec)
            acro.NeedAppearances = True
            form = _form(pdf)
            for spec in options.fields:
                if spec.default and spec.type in ("text", "multiline", "dropdown"):
                    _fill(pdf, form, spec.name, spec.default)
            return [save_pdf(pdf, ctx.output_path(f"{stem(inputs[0])}-form.pdf"))]

    def _add(self, pdf: pikepdf.Pdf, spec: FormFieldSpec) -> None:
        page = pdf.pages[spec.page - 1]
        rect = user_rect(page, spec.x, spec.y, spec.width, spec.height)
        rotation = page_rotation(page)
        w, h = rect[2] - rect[0], rect[3] - rect[1]
        if rotation in (90, 270):
            w, h = h, w
        flags = FF_REQUIRED if spec.required else 0
        widget = pikepdf.Dictionary(
            Type=pikepdf.Name.Annot,
            Subtype=pikepdf.Name.Widget,
            Rect=rect,
            F=WIDGET_PRINT,
            P=page.obj,
            MK=pikepdf.Dictionary(BC=[0.6, 0.6, 0.6], BG=[1, 1, 1], R=rotation),
        )
        da = pikepdf.String(f"/Helv {spec.font_size:g} Tf 0 g")

        widget.T = pikepdf.String(spec.name)
        if spec.type in ("text", "multiline"):
            widget.FT = pikepdf.Name.Tx
            widget.DA = da
            widget.Ff = flags | (FF_MULTILINE if spec.type == "multiline" else 0)
        elif spec.type == "dropdown":
            widget.FT = pikepdf.Name.Ch
            widget.DA = da
            widget.Opt = pikepdf.Array([pikepdf.String(o) for o in spec.options])
            widget.Ff = flags | FF_COMBO
        elif spec.type == "checkbox":
            widget.FT = pikepdf.Name.Btn
            widget.V = widget.AS = pikepdf.Name.Off
            widget.AP = pikepdf.Dictionary(
                N=pikepdf.Dictionary(
                    Yes=_stream(pdf, w, h, _box(w, h) + _check_mark(w, h)), Off=_stream(pdf, w, h, _box(w, h))
                )
            )
            widget.Ff = flags
            widget.MK.CA = pikepdf.String("4")
        elif spec.type == "signature":
            widget.FT = pikepdf.Name.Sig
        elif spec.type == "radio":
            field = pdf.make_indirect(pikepdf.Dictionary(
                FT=pikepdf.Name.Btn, T=pikepdf.String(spec.name), Ff=flags | FF_RADIO | FF_NO_TOGGLE_OFF,
                V=pikepdf.Name.Off, Kids=pikepdf.Array(),
            ))  # fmt: skip
            # One button per option, stacked down the box; labels are printed beside each button.
            self._radio_kids(pdf, page, field, spec, spec.height / len(spec.options))
            pdf.Root.AcroForm.Fields.append(field)
            return

        # Every type but radio is a merged field + widget dictionary.
        widget = pdf.make_indirect(widget)
        _ensure(page.obj, "/Annots", pikepdf.Array()).append(widget)
        pdf.Root.AcroForm.Fields.append(widget)

    def _radio_kids(self, pdf: pikepdf.Pdf, page: pikepdf.Page, parent, spec: FormFieldSpec, row: float) -> None:
        vw, vh = visual_size(page)
        size = min(row * vh, 18) / vh  # button height as a fraction of the page
        labels: list[tuple[float, float, str]] = []
        for i, option in enumerate(spec.options):
            top = spec.y + i * row + (row - size) / 2
            rect = user_rect(page, spec.x, top, size * vh / vw, size)
            w = h = size * vh
            state = pikepdf.Name("/" + _state_name(option, i))
            kid = pdf.make_indirect(
                pikepdf.Dictionary(
                    Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Widget, Rect=rect, F=WIDGET_PRINT, P=page.obj,
                    Parent=parent, AS=pikepdf.Name.Off,
                    MK=pikepdf.Dictionary(
                        BC=[0.6, 0.6, 0.6], BG=[1, 1, 1], R=page_rotation(page), CA=pikepdf.String("l")
                    ),
                    AP=pikepdf.Dictionary(N=pikepdf.Dictionary({
                        str(state): _stream(pdf, w, h, _box(w, h) + _check_mark(w, h, round_=True)),
                        "/Off": _stream(pdf, w, h, _box(w, h)),
                    })),
                )
            )  # fmt: skip
            parent.Kids.append(kid)
            _ensure(page.obj, "/Annots", pikepdf.Array()).append(kid)
            labels.append((spec.x + size * vh / vw + 0.008, top, option))

        def draw(c: Canvas, _index: int, pw: float, ph: float) -> None:
            fs = max(7.0, min(11.0, size * ph * 0.75))
            c.setFont("Helvetica", fs)
            for lx, ly, text in labels:
                c.drawString(lx * pw, ph - ly * ph - size * ph * 0.78, text)

        stamp_pages(pdf, draw, {spec.page - 1})


def _state_name(option: str, index: int) -> str:
    """A PDF name for a radio option: its text when that is a safe name, otherwise its position."""
    safe = "".join(ch for ch in option if ch.isalnum() or ch in "-_.")
    return safe or f"Choice{index + 1}"
