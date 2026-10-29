"use client";

import { FilePlus2, RotateCcw, RotateCw, Trash2, Undo2 } from "lucide-react";
import { useEffect, useState } from "react";

import type { OptionValues } from "../OptionsForm";

type Ref = { key: string; file: number; page: number | null; rotate: 0 | 90 | 180 | 270; thumb?: string };

/** Visual page editor: drag to reorder, rotate, delete, insert blank pages, across all uploaded PDFs. */
export function PageOrganizer({ files, values, onChange }: { files: File[]; values: OptionValues; onChange: (v: OptionValues) => void }) {
  const [refs, setRefs] = useState<Ref[]>([]);
  const [initial, setInitial] = useState<Ref[]>([]);
  const [loading, setLoading] = useState(true);
  const [dragging, setDragging] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    (async () => {
      const { openPdf, renderPage } = await import("@/lib/pdfjs");
      const all: Ref[] = [];
      for (const [f, file] of files.entries()) {
        try {
          const doc = await openPdf(await file.arrayBuffer());
          for (let p = 1; p <= doc.numPages && !cancelled; p++) {
            const canvas = await renderPage(doc, p, 0.25);
            all.push({ key: `${f}-${p}`, file: f, page: p, rotate: 0, thumb: canvas.toDataURL("image/jpeg", 0.75) });
          }
          await doc.destroy();
        } catch {
          /* unreadable file: the server will report it */
        }
      }
      if (!cancelled) {
        setRefs(all);
        setInitial(all);
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [files]);

  useEffect(() => {
    const pages = refs.map(({ file, page, rotate }) => ({ file, page, rotate }));
    if (JSON.stringify(pages) !== JSON.stringify(values.pages)) onChange({ ...values, pages });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refs]);

  const update = (i: number, patch: Partial<Ref>) => setRefs(refs.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  const turn = (r: Ref, by: number) => (((r.rotate + by + 360) % 360) as Ref["rotate"]);
  const move = (from: number, to: number) => {
    const next = [...refs];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    setRefs(next);
  };

  if (loading) return <div className="grid grid-cols-3 gap-3 sm:grid-cols-5">{Array.from({ length: 10 }, (_, i) => <div key={i} className="aspect-[3/4] animate-pulse rounded-lg bg-slate-200 dark:bg-slate-800" />)}</div>;

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-500">
          {refs.length} pages. Drag to reorder. Hover a page to rotate or delete it.
        </p>
        <div className="flex gap-2">
          <button className="btn-secondary px-3 py-1.5" onClick={() => setRefs(refs.map((r) => ({ ...r, rotate: turn(r, 90) })))}>
            <RotateCw className="h-4 w-4" /> Rotate all
          </button>
          <button className="btn-ghost px-3 py-1.5" onClick={() => setRefs(initial)}>
            <Undo2 className="h-4 w-4" /> Reset
          </button>
        </div>
      </div>
      <ol className="grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-6">
        {refs.map((r, i) => (
          <li
            key={r.key}
            draggable
            onDragStart={() => setDragging(i)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={() => {
              if (dragging !== null) move(dragging, i);
              setDragging(null);
            }}
            className={`group relative cursor-grab rounded-lg border border-slate-200 bg-white p-2 dark:border-slate-700 dark:bg-slate-900 ${dragging === i ? "opacity-40" : ""}`}
          >
            <div className="flex aspect-[3/4] items-center justify-center overflow-hidden">
              {r.thumb ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={r.thumb} alt="" draggable={false} className="max-h-full max-w-full shadow transition" style={{ transform: `rotate(${r.rotate}deg)` }} />
              ) : (
                <div className="h-full w-full rounded bg-white ring-1 ring-slate-200" />
              )}
            </div>
            <p className="mt-1 text-center text-xs text-slate-500">
              {r.page ? (files.length > 1 ? `File ${r.file + 1} · p${r.page}` : `Page ${r.page}`) : "Blank"}
            </p>
            <div className="absolute inset-x-0 top-1 flex justify-center gap-1 opacity-0 transition group-hover:opacity-100">
              <button className="rounded-md bg-white p-1 shadow ring-1 ring-slate-200 dark:bg-slate-800" aria-label="Rotate left" onClick={() => update(i, { rotate: turn(r, -90) })}>
                <RotateCcw className="h-3.5 w-3.5" />
              </button>
              <button className="rounded-md bg-white p-1 shadow ring-1 ring-slate-200 dark:bg-slate-800" aria-label="Rotate right" onClick={() => update(i, { rotate: turn(r, 90) })}>
                <RotateCw className="h-3.5 w-3.5" />
              </button>
              <button className="rounded-md bg-white p-1 shadow ring-1 ring-slate-200 dark:bg-slate-800" aria-label="Insert blank page after" onClick={() => setRefs([...refs.slice(0, i + 1), { key: `blank-${Date.now()}`, file: r.file, page: null, rotate: 0 }, ...refs.slice(i + 1)])}>
                <FilePlus2 className="h-3.5 w-3.5" />
              </button>
              <button className="rounded-md bg-white p-1 text-rose-600 shadow ring-1 ring-slate-200 dark:bg-slate-800" aria-label="Delete page" onClick={() => setRefs(refs.filter((_, k) => k !== i))}>
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
