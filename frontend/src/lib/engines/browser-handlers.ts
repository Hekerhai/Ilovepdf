/** pdf-lib / pdf.js implementations, loaded only when a tool actually runs in the browser. */
import {
  concatTransformationMatrix,
  degrees,
  LineCapStyle,
  PDFCheckBox,
  PDFDocument,
  PDFDropdown,
  type PDFFont,
  type PDFImage,
  PDFOptionList,
  type PDFPage,
  PDFRadioGroup,
  PDFTextField,
  popGraphicsState,
  pushGraphicsState,
  rgb,
  StandardFonts,
} from "pdf-lib";

import { stem } from "../format";
import { parsePageList, parseRangeGroups } from "../pages";
import { type Box, userRect, visualSize, visualToUser } from "./geometry";
import type { Options, Progress } from "./types";

export type Output = { name: string; bytes: Uint8Array; type: string };
type Handler = (files: File[], o: Options, progress: Progress) => Promise<Output[]>;

const PDF_TYPE = "application/pdf";
const MM = 72 / 25.4;
const PAGE_SIZES: Record<string, [number, number]> = { A4: [210 * MM, 297 * MM], Letter: [612, 792] };

async function load(file: File): Promise<PDFDocument> {
  try {
    return await PDFDocument.load(await file.arrayBuffer());
  } catch (e) {
    const msg = String((e as Error)?.message ?? e);
    if (/encrypt/i.test(msg)) throw new Error(`'${file.name}' is password protected. Unlock it first.`);
    throw new Error(`'${file.name}' is not a readable PDF.`);
  }
}

async function pick(src: PDFDocument, indexes: number[]): Promise<Uint8Array> {
  const out = await PDFDocument.create();
  const pages = await out.copyPages(src, indexes);
  pages.forEach((p) => out.addPage(p));
  return out.save();
}

const pdf = (name: string, bytes: Uint8Array): Output => ({ name, bytes, type: PDF_TYPE });

/** Tools that run entirely on the user's device with pdf-lib and pdf.js. Files never leave the browser. */
export const handlers: Record<string, Handler> = {
  async merge(files, _o, progress) {
    const out = await PDFDocument.create();
    for (const [i, file] of files.entries()) {
      progress(`Adding ${file.name}…`, i / files.length);
      const src = await load(file);
      (await out.copyPages(src, src.getPageIndices())).forEach((p) => out.addPage(p));
    }
    return [pdf("merged.pdf", await out.save())];
  },

  async split([file], o) {
    const src = await load(file);
    const total = src.getPageCount();
    const base = stem(file.name);
    let groups: number[][];
    if (o.mode === "every") {
      const n = Math.max(1, Number(o.every ?? 1));
      groups = [];
      for (let i = 0; i < total; i += n) groups.push([...Array(Math.min(n, total - i)).keys()].map((k) => k + i));
    } else if (o.mode === "all") {
      groups = [...Array(total).keys()].map((i) => [i]);
    } else {
      groups = parseRangeGroups(String(o.ranges ?? "1"), total);
    }
    if (o.merge_output && (o.mode ?? "ranges") === "ranges") {
      return [pdf(`${base}-extracted.pdf`, await pick(src, groups.flat()))];
    }
    const outs: Output[] = [];
    for (const [n, g] of groups.entries()) outs.push(pdf(`${base}-${String(n + 1).padStart(3, "0")}.pdf`, await pick(src, g)));
    return outs;
  },

  async remove_pages([file], o) {
    const src = await load(file);
    const drop = new Set(parsePageList(String(o.pages ?? ""), src.getPageCount()));
    const keep = src.getPageIndices().filter((i) => !drop.has(i));
    if (!keep.length) throw new Error("You can't remove every page.");
    return [pdf(`${stem(file.name)}.pdf`, await pick(src, keep))];
  },

  async extract_pages([file], o) {
    const src = await load(file);
    return [pdf(`${stem(file.name)}-pages.pdf`, await pick(src, parsePageList(String(o.pages ?? ""), src.getPageCount())))];
  },

  async rotate(files, o) {
    const outs: Output[] = [];
    for (const file of files) {
      const doc = await load(file);
      for (const i of new Set(parsePageList(String(o.pages ?? "all"), doc.getPageCount()))) {
        const page = doc.getPage(i);
        page.setRotation(degrees((page.getRotation().angle + Number(o.angle ?? 90)) % 360));
      }
      outs.push(pdf(`${stem(file.name)}.pdf`, await doc.save()));
    }
    return outs;
  },

  async organize(files, o) {
    const sources = await Promise.all(files.map(load));
    const out = await PDFDocument.create();
    for (const ref of (o.pages as { file?: number; page?: number | null; rotate?: number }[]) ?? []) {
      const src = sources[ref.file ?? 0];
      if (!src) throw new Error(`File #${(ref.file ?? 0) + 1} was not uploaded.`);
      let page;
      if (ref.page == null) {
        const first = src.getPage(0);
        page = out.addPage([first.getWidth(), first.getHeight()]);
      } else {
        [page] = await out.copyPages(src, [ref.page - 1]);
        out.addPage(page);
      }
      if (ref.rotate) page.setRotation(degrees((page.getRotation().angle + ref.rotate) % 360));
    }
    return [pdf(`${stem(files[0].name)}-organized.pdf`, await out.save())];
  },

  async images_to_pdf(files, o, progress) {
    const single = o.single_file !== false;
    const outs: Output[] = [];
    let doc = await PDFDocument.create();
    for (const [i, file] of files.entries()) {
      progress(`Adding ${file.name}…`, i / files.length);
      await addImagePage(doc, file, o);
      if (!single) {
        outs.push(pdf(`${stem(file.name)}.pdf`, await doc.save()));
        doc = await PDFDocument.create();
      }
    }
    if (single) outs.push(pdf(`${stem(files[0].name)}.pdf`, await doc.save()));
    return outs;
  },

  async pdf_to_images(files, o, progress) {
    const { openPdf, renderPage, canvasToBlob } = await import("../pdfjs");
    const format = o.format === "png" ? "png" : "jpg";
    const scale = Number(o.dpi ?? 150) / 72;
    const outs: Output[] = [];
    for (const file of files) {
      const doc = await openPdf(await file.arrayBuffer());
      const pages = parsePageList(String(o.pages ?? "all"), doc.numPages);
      for (const [n, index] of pages.entries()) {
        progress(`Rendering page ${index + 1}…`, n / pages.length);
        const canvas = await renderPage(doc, index + 1, scale);
        const blob = await canvasToBlob(canvas, format === "png" ? "image/png" : "image/jpeg", Number(o.quality ?? 90) / 100);
        outs.push({
          name: `${stem(file.name)}-page-${String(index + 1).padStart(3, "0")}.${format}`,
          bytes: new Uint8Array(await blob.arrayBuffer()),
          type: blob.type,
        });
      }
      await doc.destroy();
    }
    return outs;
  },

  async edit_pdf([file], o) {
    const doc = await load(file);
    const fonts = new FontCache(doc);
    const byPage = groupByPage((o.objects as EditObject[]) ?? []);
    for (const [index, objects] of byPage) {
      if (index >= doc.getPageCount()) throw new Error(`Page ${index + 1} doesn't exist; this PDF has ${doc.getPageCount()}.`);
      const page = doc.getPage(index);
      await inVisualSpace(page, async (w, h) => {
        for (const obj of objects) await drawObject(doc, page, fonts, obj, w, h);
      });
    }
    if (o.flatten) doc.getForm().flatten();
    return [pdf(`${stem(file.name)}-edited.pdf`, await doc.save())];
  },

  async fill_forms([file], o) {
    const doc = await load(file);
    const form = doc.getForm();
    if (!form.getFields().length) throw new Error("This PDF has no fillable fields. Use Create forms to add some.");
    for (const [name, value] of Object.entries((o.fields as Record<string, string | boolean>) ?? {})) {
      const field = form.getFieldMaybe(name);
      if (!field) throw new Error(`No field named '${name}' in this PDF.`);
      const text = value === false ? "" : String(value);
      if (field instanceof PDFTextField) field.setText(text);
      else if (field instanceof PDFCheckBox) (value === true || /^(true|yes|on|1)$/i.test(text) ? field.check() : field.uncheck());
      else if (field instanceof PDFRadioGroup) field.select(text);
      else if (field instanceof PDFDropdown || field instanceof PDFOptionList) field.select(text);
    }
    if (o.flatten) form.flatten();
    return [pdf(`${stem(file.name)}-filled.pdf`, await doc.save())];
  },

  async create_forms([file], o) {
    const doc = await load(file);
    const form = doc.getForm();
    const specs = (o.fields as FieldSpec[]) ?? [];
    const names = specs.map((f) => f.name);
    if (new Set(names).size !== names.length) throw new Error("Each field needs a unique name.");
    const existing = new Set(form.getFields().map((f) => f.getName()));
    const clash = names.find((n) => existing.has(n));
    if (clash) throw new Error(`This PDF already has a field named '${clash}'.`);
    const helvetica = await doc.embedFont(StandardFonts.Helvetica);
    for (const spec of specs) {
      if (spec.page > doc.getPageCount()) throw new Error(`Page ${spec.page} doesn't exist; this PDF has ${doc.getPageCount()}.`);
      const page = doc.getPage(spec.page - 1);
      const rotation = page.getRotation().angle;
      const crop = page.getCropBox();
      const rect = userRect(rotation, crop, spec);
      const look = { ...rect, borderColor: rgb(0.6, 0.6, 0.6), backgroundColor: rgb(1, 1, 1), borderWidth: 1, font: helvetica };
      if (spec.type === "text" || spec.type === "multiline") {
        const field = form.createTextField(spec.name);
        if (spec.type === "multiline") field.enableMultiline();
        if (spec.default) field.setText(spec.default);
        if (spec.required) field.enableRequired();
        field.addToPage(page, look);
        if (spec.font_size) field.setFontSize(spec.font_size);
      } else if (spec.type === "checkbox") {
        const field = form.createCheckBox(spec.name);
        if (spec.required) field.enableRequired();
        field.addToPage(page, look);
      } else if (spec.type === "dropdown") {
        const field = form.createDropdown(spec.name);
        field.setOptions(spec.options ?? []);
        if (spec.default) field.select(spec.default);
        if (spec.required) field.enableRequired();
        field.addToPage(page, look);
        if (spec.font_size) field.setFontSize(spec.font_size);
      } else if (spec.type === "radio") {
        const group = form.createRadioGroup(spec.name);
        if (spec.required) group.enableRequired();
        const options = spec.options ?? [];
        const [vw, vh] = visualSize(rotation, crop);
        const row = spec.height / options.length;
        const size = Math.min(row * vh, 18) / vh;
        const labels: [number, number, string][] = [];
        options.forEach((option, i) => {
          const top = spec.y + i * row + (row - size) / 2;
          const box = { x: spec.x, y: top, width: (size * vh) / vw, height: size };
          group.addOptionToPage(radioStateName(option, i), page, { ...look, ...userRect(rotation, crop, box) });
          labels.push([spec.x + (size * vh) / vw + 0.008, top, option]);
        });
        await inVisualSpace(page, (w, h) => {
          const fs = Math.max(7, Math.min(11, size * h * 0.75));
          for (const [lx, ly, text] of labels) page.drawText(text, { x: lx * w, y: h - ly * h - size * h * 0.78, size: fs, font: helvetica });
        });
      } else {
        throw new Error("Signature fields are added on our servers.");
      }
    }
    return [pdf(`${stem(file.name)}-form.pdf`, await doc.save())];
  },

  async scan_to_pdf(files, o, progress) {
    const single = o.single_file !== false;
    const outs: Output[] = [];
    let doc = await PDFDocument.create();
    for (const [i, file] of files.entries()) {
      progress(`Cleaning up ${file.name}…`, i / files.length);
      const cleaned = await cleanScan(file, String(o.filter ?? "enhanced"));
      await addImagePage(doc, cleaned, { page_size: "A4", ...o });
      if (!single) {
        outs.push(pdf(`${stem(file.name)}-scan.pdf`, await doc.save()));
        doc = await PDFDocument.create();
      }
    }
    if (single) outs.push(pdf(`${stem(files[0].name)}-scan.pdf`, await doc.save()));
    return outs;
  },
};

async function addImagePage(doc: PDFDocument, file: File, o: Options): Promise<void> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  const isJpeg = file.type === "image/jpeg" || /\.jpe?g$/i.test(file.name);
  const isPng = file.type === "image/png" || /\.png$/i.test(file.name);
  const image = isJpeg ? await doc.embedJpg(bytes) : isPng ? await doc.embedPng(bytes) : await doc.embedPng(await toPng(file));
  const margin = Number(o.margin_mm ?? 0) * MM;
  const size = String(o.page_size ?? "fit");
  if (size === "fit") {
    const page = doc.addPage([image.width + 2 * margin, image.height + 2 * margin]);
    page.drawImage(image, { x: margin, y: margin, width: image.width, height: image.height });
    return;
  }
  const [w, h] = PAGE_SIZES[size];
  const landscape = o.orientation === "landscape" || (o.orientation !== "portrait" && image.width > image.height);
  const [pw, ph] = landscape ? [Math.max(w, h), Math.min(w, h)] : [Math.min(w, h), Math.max(w, h)];
  const scale = Math.min((pw - 2 * margin) / image.width, (ph - 2 * margin) / image.height);
  const page = doc.addPage([pw, ph]);
  const iw = image.width * scale;
  const ih = image.height * scale;
  page.drawImage(image, { x: (pw - iw) / 2, y: (ph - ih) / 2, width: iw, height: ih });
}

async function toPng(file: File): Promise<Uint8Array> {
  const bitmap = await createImageBitmap(file);
  const canvas = document.createElement("canvas");
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(bitmap, 0, 0);
  const blob = await new Promise<Blob>((res, rej) => canvas.toBlob((b) => (b ? res(b) : rej(new Error("Image conversion failed"))), "image/png"));
  return new Uint8Array(await blob.arrayBuffer());
}


// ---- Edit PDF ---------------------------------------------------------------------------------------------------

export type EditObject = {
  // underline, strikeout and note exist only as annotations (Annotate PDF), never drawn into the page.
  type: "text" | "image" | "rect" | "ellipse" | "line" | "arrow" | "highlight" | "whiteout" | "draw" | "underline" | "strikeout" | "note";
  page: number;
  x: number;
  y: number;
  width?: number;
  height?: number;
  x2?: number | null;
  y2?: number | null;
  points?: [number, number][] | null;
  text?: string | null;
  font?: "sans" | "serif" | "mono";
  font_size?: number;
  bold?: boolean;
  italic?: boolean;
  color?: string;
  fill?: string | null;
  stroke_width?: number;
  opacity?: number;
  image?: string | null;
  /** Annotate PDF: the comment shown in the reader's comments panel. */
  comment?: string | null;
};

// Must match backend/app/tools/editor.py so text lands in the same place on both engines.
const ASCENT = 0.8;
const LINE_HEIGHT = 1.2;

const STANDARD: Record<string, StandardFonts[]> = {
  // regular, bold, italic, bold italic
  sans: [StandardFonts.Helvetica, StandardFonts.HelveticaBold, StandardFonts.HelveticaOblique, StandardFonts.HelveticaBoldOblique],
  serif: [StandardFonts.TimesRoman, StandardFonts.TimesRomanBold, StandardFonts.TimesRomanItalic, StandardFonts.TimesRomanBoldItalic],
  mono: [StandardFonts.Courier, StandardFonts.CourierBold, StandardFonts.CourierOblique, StandardFonts.CourierBoldOblique],
};

class FontCache {
  private fonts = new Map<StandardFonts, PDFFont>();
  constructor(private doc: PDFDocument) {}
  async get(obj: EditObject): Promise<PDFFont> {
    const name = STANDARD[obj.font ?? "sans"][(obj.bold ? 1 : 0) + (obj.italic ? 2 : 0)];
    if (!this.fonts.has(name)) this.fonts.set(name, await this.doc.embedFont(name));
    return this.fonts.get(name)!;
  }
}

function groupByPage<T extends { page: number }>(items: T[]): Map<number, T[]> {
  const out = new Map<number, T[]>();
  for (const item of items) out.set(item.page - 1, [...(out.get(item.page - 1) ?? []), item]);
  return out;
}

/** Run drawing code in visual coordinates (bottom-left origin, page rotation applied), as the reader sees the page. */
async function inVisualSpace(page: PDFPage, draw: (w: number, h: number) => void | Promise<void>) {
  const rotation = page.getRotation().angle;
  const crop: Box = page.getCropBox();
  const [w, h] = visualSize(rotation, crop);
  page.pushOperators(pushGraphicsState(), concatTransformationMatrix(...visualToUser(rotation, crop)));
  await draw(w, h);
  page.pushOperators(popGraphicsState());
}

function hex(value: string | null | undefined, fallback = "#111827") {
  const v = (value || fallback).replace("#", "");
  return rgb(parseInt(v.slice(0, 2), 16) / 255, parseInt(v.slice(2, 4), 16) / 255, parseInt(v.slice(4, 6), 16) / 255);
}

async function embedDataUrl(doc: PDFDocument, dataUrl: string): Promise<PDFImage> {
  const bytes = Uint8Array.from(atob(dataUrl.split(",", 2)[1] ?? ""), (c) => c.charCodeAt(0));
  if (/^data:image\/png/i.test(dataUrl)) return doc.embedPng(bytes);
  if (/^data:image\/jpe?g/i.test(dataUrl)) return doc.embedJpg(bytes);
  return doc.embedPng(await toPng(new File([bytes], "image")));
}

async function drawObject(doc: PDFDocument, page: PDFPage, fonts: FontCache, obj: EditObject, w: number, h: number) {
  const x = obj.x * w;
  const top = h - obj.y * h;
  const bw = (obj.width ?? 0) * w;
  const bh = (obj.height ?? 0) * h;
  const opacity = obj.opacity ?? 1;
  const stroke = hex(obj.color);
  const thickness = obj.stroke_width ?? 2;
  switch (obj.type) {
    case "text": {
      const size = obj.font_size ?? 14;
      page.drawText(obj.text ?? "", { x, y: top - size * ASCENT, size, font: await fonts.get(obj), color: stroke, opacity, lineHeight: size * LINE_HEIGHT });
      break;
    }
    case "image":
      page.drawImage(await embedDataUrl(doc, obj.image ?? ""), { x, y: top - bh, width: bw, height: bh, opacity });
      break;
    case "rect":
    case "ellipse": {
      const look = {
        borderColor: thickness > 0 ? stroke : undefined,
        borderWidth: thickness,
        borderOpacity: opacity,
        color: obj.fill ? hex(obj.fill) : undefined,
        opacity,
      };
      if (obj.type === "rect") page.drawRectangle({ x, y: top - bh, width: bw, height: bh, ...look });
      else page.drawEllipse({ x: x + bw / 2, y: top - bh / 2, xScale: bw / 2, yScale: bh / 2, ...look });
      break;
    }
    case "highlight":
    case "whiteout": {
      const fill = obj.fill || (obj.type === "highlight" ? "#FDE047" : "#FFFFFF");
      page.drawRectangle({ x, y: top - bh, width: bw, height: bh, color: hex(fill), opacity: obj.type === "highlight" ? Math.min(opacity, 0.4) : opacity });
      break;
    }
    case "line":
    case "arrow": {
      const x2 = (obj.x2 ?? 0) * w;
      const y2 = h - (obj.y2 ?? 0) * h;
      const line = { thickness, color: stroke, opacity, lineCap: LineCapStyle.Round };
      page.drawLine({ start: { x, y: top }, end: { x: x2, y: y2 }, ...line });
      if (obj.type === "arrow") {
        const head = Math.max(8, thickness * 4);
        const angle = Math.atan2(y2 - top, x2 - x);
        for (const side of [-1, 1]) {
          const a = angle + Math.PI - (side * Math.PI) / 7;
          page.drawLine({ start: { x: x2, y: y2 }, end: { x: x2 + head * Math.cos(a), y: y2 + head * Math.sin(a) }, ...line });
        }
      }
      break;
    }
    case "draw": {
      // SVG paths in pdf-lib use a y-down space anchored at (x, y), which matches our top-left fractions.
      const d = (obj.points ?? []).map(([px, py], i) => `${i ? "L" : "M"}${(px * w).toFixed(2)} ${(py * h).toFixed(2)}`).join(" ");
      if (d) page.drawSvgPath(d, { x: 0, y: h, borderColor: stroke, borderWidth: thickness, borderOpacity: opacity, borderLineCap: LineCapStyle.Round });
      break;
    }
  }
}

// ---- Forms ------------------------------------------------------------------------------------------------------

export type FieldSpec = Box & {
  type: "text" | "multiline" | "checkbox" | "dropdown" | "radio" | "signature";
  name: string;
  page: number;
  options?: string[];
  required?: boolean;
  default?: string | null;
  font_size?: number;
};

/** A PDF name for a radio option; matches _state_name in backend/app/tools/editor.py. */
export function radioStateName(option: string, index: number): string {
  const safe = [...option].filter((ch) => /[\p{L}\p{N}\-_.]/u.test(ch)).join("");
  return safe || `Choice${index + 1}`;
}

// ---- Scan to PDF ------------------------------------------------------------------------------------------------

/** Make a phone photo of a document look scanned. Mirrors clean_scan in backend/app/tools/convert_to.py. */
async function cleanScan(file: File, mode: string): Promise<File> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, 2480 / Math.max(bitmap.width, bitmap.height));
  const width = Math.round(bitmap.width * scale);
  const height = Math.round(bitmap.height * scale);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(bitmap, 0, 0, width, height);
  const image = ctx.getImageData(0, 0, width, height);
  const px = image.data;
  const n = width * height;
  const gray = new Float32Array(n);
  for (let i = 0; i < n; i++) gray[i] = 0.299 * px[i * 4] + 0.587 * px[i * 4 + 1] + 0.114 * px[i * 4 + 2];

  let values: Float32Array | null = null;
  if (mode === "enhanced" || mode === "black_white") {
    // Very blurred copy (shrink, then smooth back up) = the lighting; dividing by it removes shadows.
    const small = document.createElement("canvas");
    small.width = Math.max(1, Math.round(width / 40));
    small.height = Math.max(1, Math.round(height / 40));
    const sctx = small.getContext("2d")!;
    sctx.drawImage(canvas, 0, 0, small.width, small.height);
    const blurred = document.createElement("canvas");
    blurred.width = width;
    blurred.height = height;
    const bctx = blurred.getContext("2d", { willReadFrequently: true })!;
    bctx.imageSmoothingQuality = "high";
    bctx.filter = "blur(8px)";
    bctx.drawImage(small, 0, 0, width, height);
    const bg = bctx.getImageData(0, 0, width, height).data;
    values = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const b = 0.299 * bg[i * 4] + 0.587 * bg[i * 4 + 1] + 0.114 * bg[i * 4 + 2];
      values[i] = Math.min(255, (gray[i] * 245) / Math.max(b, 1));
    }
  } else if (mode === "grayscale") {
    values = gray;
  }

  if (values) {
    const [lo, hi] = percentiles(values, 0.02, 0.99);
    const span = Math.max(1, hi - lo);
    for (let i = 0; i < n; i++) {
      let v = ((values[i] - lo) * 255) / span;
      if (mode === "black_white") v = v > 165 ? 255 : 0;
      px[i * 4] = px[i * 4 + 1] = px[i * 4 + 2] = Math.max(0, Math.min(255, v));
    }
  } else {
    const [lo, hi] = percentiles(gray, 0.01, 0.99);
    const span = Math.max(1, hi - lo);
    for (let i = 0; i < n * 4; i++) if (i % 4 !== 3) px[i] = Math.max(0, Math.min(255, ((px[i] - lo) * 255) / span));
  }
  ctx.putImageData(image, 0, 0);
  const png = mode === "black_white";
  const blob = await new Promise<Blob>((res, rej) =>
    canvas.toBlob((b) => (b ? res(b) : rej(new Error("Image conversion failed"))), png ? "image/png" : "image/jpeg", 0.85),
  );
  return new File([blob], `${stem(file.name)}.${png ? "png" : "jpg"}`, { type: blob.type });
}

function percentiles(values: Float32Array, low: number, high: number): [number, number] {
  const hist = new Uint32Array(256);
  for (const v of values) hist[Math.max(0, Math.min(255, Math.round(v)))]++;
  const total = values.length;
  let acc = 0;
  let lo = 0;
  let hi = 255;
  for (let i = 0; i < 256; i++) {
    acc += hist[i];
    if (acc <= total * low) lo = i;
    if (acc < total * high) hi = i + 1;
  }
  return [lo, Math.max(lo + 1, hi)];
}
