"use client";

import { useEffect, useState } from "react";

/** Render every page of a PDF to small data-URL thumbnails (plus page sizes). */
export function usePdfPages(file: File | undefined, scale = 0.3) {
  const [pages, setPages] = useState<{ src: string; width: number; height: number }[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!file) return;
    let cancelled = false;
    setPages([]);
    setError(null);
    (async () => {
      try {
        const { openPdf, renderPage } = await import("@/lib/pdfjs");
        const doc = await openPdf(await file.arrayBuffer());
        const out = [];
        for (let i = 1; i <= doc.numPages && !cancelled; i++) {
          const canvas = await renderPage(doc, i, scale);
          out.push({ src: canvas.toDataURL("image/jpeg", 0.8), width: canvas.width, height: canvas.height });
          if (i % 4 === 0 || i === doc.numPages) setPages([...out]);
        }
        await doc.destroy();
      } catch {
        if (!cancelled) setError("Couldn't preview this PDF. It may be password protected.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [file, scale]);

  return { pages, error };
}
