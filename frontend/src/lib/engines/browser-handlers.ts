/** pdf-lib / pdf.js implementations, loaded only when a tool actually runs in the browser. */
import { degrees, PDFDocument } from "pdf-lib";

import { stem } from "../format";
import { parsePageList, parseRangeGroups } from "../pages";
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

