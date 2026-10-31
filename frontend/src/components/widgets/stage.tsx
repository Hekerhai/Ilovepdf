"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";

type PdfDoc = Awaited<ReturnType<typeof import("@/lib/pdfjs").openPdf>>;

export type PageView = {
  src: string;
  /** Visual page size in PDF points (rotation applied), so overlays can work in points like the PDF does. */
  width: number;
  height: number;
};

/** Render one page at a time with pdf.js, keeping the document open between pages. */
export function usePdfPage(file: File | undefined, page: number, scale = 1.5) {
  const doc = useRef<PdfDoc | null>(null);
  const [count, setCount] = useState(0);
  const [view, setView] = useState<PageView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!file) return;
    let cancelled = false;
    setView(null);
    setError(null);
    (async () => {
      try {
        const { openPdf } = await import("@/lib/pdfjs");
        const opened = await openPdf(await file.arrayBuffer());
        if (cancelled) return opened.destroy();
        doc.current = opened;
        setCount(opened.numPages);
      } catch {
        if (!cancelled) setError("Couldn't open this PDF. It may be password protected or damaged.");
      }
    })();
    return () => {
      cancelled = true;
      doc.current?.destroy();
      doc.current = null;
      setCount(0);
    };
  }, [file]);

  useEffect(() => {
    if (!count || !doc.current) return;
    let cancelled = false;
    (async () => {
      const { renderPage } = await import("@/lib/pdfjs");
      const current = doc.current;
      if (!current) return;
      const canvas = await renderPage(current, Math.min(page, count), scale);
      if (!cancelled) setView({ src: canvas.toDataURL("image/png"), width: canvas.width / scale, height: canvas.height / scale });
    })();
    return () => {
      cancelled = true;
    };
  }, [count, page, scale]);

  return { view, count, error };
}

/** Pointer position as fractions of an element's box (0..1, origin top-left). */
export function fractionAt(e: { clientX: number; clientY: number }, el: Element): [number, number] {
  const r = el.getBoundingClientRect();
  return [(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height];
}

export const clamp = (v: number, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, v));

/** A page image with an overlay slot and page navigation underneath. */
export function PageStage({
  view,
  page,
  count,
  onPage,
  children,
  footer,
}: {
  view: PageView | null;
  page: number;
  count: number;
  onPage: (page: number) => void;
  children?: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div>
      {view ? (
        <div className="relative mx-auto max-w-2xl select-none overflow-hidden rounded-lg border border-slate-300 bg-white shadow dark:border-slate-700">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={view.src} alt={`Page ${page}`} className="block w-full" draggable={false} />
          <div className="absolute inset-0">{children}</div>
        </div>
      ) : (
        <div className="mx-auto aspect-[1/1.41] max-w-2xl animate-pulse rounded-lg bg-slate-200 dark:bg-slate-800" />
      )}
      <div className="mt-3 flex flex-wrap items-center justify-center gap-2 text-sm">
        {count > 1 && (
          <>
            <button className="btn-secondary px-2 py-1.5" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page">
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span>
              Page {page} of {count}
            </span>
            <button className="btn-secondary px-2 py-1.5" disabled={page >= count} onClick={() => onPage(page + 1)} aria-label="Next page">
              <ChevronRight className="h-4 w-4" />
            </button>
          </>
        )}
        {footer}
      </div>
    </div>
  );
}

/** Read a file as a data URL. */
export function readDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

/** Box drag (move or resize) shared by the editor and the form builder. Works in page fractions. */
export type BoxLike = { x: number; y: number; width: number; height: number };

export function dragBox(start: BoxLike, mode: "move" | "resize", dx: number, dy: number): BoxLike {
  if (mode === "move") {
    return { ...start, x: clamp(start.x + dx, -start.width + 0.02, 0.98), y: clamp(start.y + dy, -start.height + 0.02, 0.98) };
  }
  return { ...start, width: Math.max(0.01, start.width + dx), height: Math.max(0.005, start.height + dy) };
}
