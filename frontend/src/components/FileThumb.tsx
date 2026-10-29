"use client";

import { FileText } from "lucide-react";
import { useEffect, useState } from "react";

/** First-page preview for PDFs, the image itself for images, an icon otherwise. */
export function FileThumb({ file, className = "h-28 w-20" }: { file: File; className?: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const [pages, setPages] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    let url: string | null = null;
    (async () => {
      if (file.type.startsWith("image/")) {
        url = URL.createObjectURL(file);
        if (!cancelled) setSrc(url);
        return;
      }
      if (!file.name.toLowerCase().endsWith(".pdf")) return;
      try {
        const { openPdf, renderPage } = await import("@/lib/pdfjs");
        const doc = await openPdf(await file.arrayBuffer());
        const canvas = await renderPage(doc, 1, 0.35);
        if (!cancelled) {
          setPages(doc.numPages);
          setSrc(canvas.toDataURL("image/jpeg", 0.8));
        }
        await doc.destroy();
      } catch {
        /* encrypted or broken: keep the icon */
      }
    })();
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [file]);

  return (
    <div className={`relative flex items-center justify-center overflow-hidden rounded-lg border border-slate-200 bg-slate-100 dark:border-slate-700 dark:bg-slate-800 ${className}`}>
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt="" className="h-full w-full object-contain" />
      ) : (
        <FileText className="h-8 w-8 text-slate-400" />
      )}
      {pages !== null && (
        <span className="absolute bottom-1 right-1 rounded bg-slate-900/70 px-1.5 text-[10px] font-medium text-white">{pages} p</span>
      )}
    </div>
  );
}
