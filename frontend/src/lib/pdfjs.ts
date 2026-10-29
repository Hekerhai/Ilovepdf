"use client";

import type * as PdfJs from "pdfjs-dist";

let loader: Promise<typeof PdfJs> | null = null;

/** Lazily load pdf.js (it is large and browser-only) and point it at its worker. */
export function loadPdfjs(): Promise<typeof PdfJs> {
  loader ??= import("pdfjs-dist").then((lib) => {
    lib.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();
    return lib;
  });
  return loader;
}

export async function openPdf(data: ArrayBuffer | Uint8Array, password?: string) {
  const pdfjs = await loadPdfjs();
  return pdfjs.getDocument({ data: data instanceof Uint8Array ? data : new Uint8Array(data), password }).promise;
}

/** Render one page (1-based) to a canvas at the given scale. */
export async function renderPage(
  doc: Awaited<ReturnType<typeof openPdf>>,
  pageNumber: number,
  scale: number,
  rotation = 0,
): Promise<HTMLCanvasElement> {
  const page = await doc.getPage(pageNumber);
  const viewport = page.getViewport({ scale, rotation: (page.rotate + rotation) % 360 });
  const canvas = document.createElement("canvas");
  canvas.width = Math.ceil(viewport.width);
  canvas.height = Math.ceil(viewport.height);
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  await page.render({ canvasContext: ctx, viewport }).promise;
  page.cleanup();
  return canvas;
}

export function canvasToBlob(canvas: HTMLCanvasElement, type: string, quality?: number): Promise<Blob> {
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Could not encode image"))), type, quality),
  );
}
