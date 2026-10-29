"use client";

import { Eraser, Plus, Trash2, Type, Upload, PenLine } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { OptionValues } from "../OptionsForm";
import { usePdfPages } from "./usePdfPages";

type Placement = { page: number; x: number; y: number; width: number };
type Mode = "draw" | "type" | "upload";

const INKS = ["#111827", "#1d4ed8", "#b91c1c"];

/** Create a signature (draw, type or upload) and place it on the pages with a click. */
export function SignWidget({ file, values, onChange }: { file: File; values: OptionValues; onChange: (v: OptionValues) => void }) {
  const signature = (values.signature as string) || "";
  const placements = (values.placements as Placement[]) || [];
  const { pages, error } = usePdfPages(file, 0.9);
  const [page, setPage] = useState(1);
  const [width, setWidth] = useState(0.28);
  const set = (patch: OptionValues) => onChange({ ...values, ...patch });

  const place = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!signature) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = Math.max(0, Math.min(1 - width, (e.clientX - rect.left) / rect.width - width / 2));
    const y = Math.max(0, Math.min(0.95, (e.clientY - rect.top) / rect.height - 0.03));
    set({ placements: [...placements, { page, x, y, width }] });
  };

  const current = pages[page - 1];

  return (
    <div className="space-y-5">
      <SignaturePad value={signature} onChange={(sig) => set({ signature: sig })} />
      {signature && (
        <div>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-medium">Click the page to place your signature</p>
            <div className="flex items-center gap-2 text-sm">
              <label htmlFor="sig-size">Size</label>
              <input id="sig-size" type="range" min={0.1} max={0.6} step={0.01} value={width} onChange={(e) => setWidth(Number(e.target.value))} />
            </div>
          </div>
          {error && <p className="text-sm text-rose-600">{error}</p>}
          {current ? (
            <div className="relative mx-auto max-w-xl cursor-crosshair select-none overflow-hidden rounded-lg border border-slate-300 shadow" onClick={place}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={current.src} alt={`Page ${page}`} className="w-full" draggable={false} />
              {placements.map((p, i) =>
                p.page === page ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    key={i}
                    src={signature}
                    alt="Signature"
                    title="Click to remove"
                    onClick={(e) => {
                      e.stopPropagation();
                      set({ placements: placements.filter((_, k) => k !== i) });
                    }}
                    className="absolute cursor-pointer outline outline-1 outline-dashed outline-brand-500 hover:opacity-60"
                    style={{ left: `${p.x * 100}%`, top: `${p.y * 100}%`, width: `${p.width * 100}%` }}
                  />
                ) : null,
              )}
            </div>
          ) : (
            !error && <div className="mx-auto h-96 max-w-xl animate-pulse rounded-lg bg-slate-200 dark:bg-slate-800" />
          )}
          {pages.length > 1 && (
            <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
              <button className="btn-secondary px-3 py-1.5" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                Previous
              </button>
              <span className="text-sm">
                Page {page} of {pages.length}
              </span>
              <button className="btn-secondary px-3 py-1.5" disabled={page >= pages.length} onClick={() => setPage(page + 1)}>
                Next
              </button>
              {placements.some((p) => p.page === page) && (
                <button
                  className="btn-ghost px-3 py-1.5"
                  onClick={() => {
                    const here = placements.filter((p) => p.page === page);
                    const all = pages.flatMap((_, i) => here.map((p) => ({ ...p, page: i + 1 })));
                    set({ placements: all });
                  }}
                >
                  <Plus className="h-4 w-4" /> Same spot on every page
                </button>
              )}
            </div>
          )}
          <p className="help text-center">
            {placements.length} signature{placements.length === 1 ? "" : "s"} placed. Click a signature to remove it.
          </p>
        </div>
      )}
    </div>
  );
}

function SignaturePad({ value, onChange }: { value: string; onChange: (dataUrl: string) => void }) {
  const [mode, setMode] = useState<Mode>("draw");
  const [ink, setInk] = useState(INKS[0]);
  const [typed, setTyped] = useState("");
  const canvas = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const dirty = useRef(false);

  useEffect(() => {
    if (mode !== "type") return;
    if (!typed.trim()) return;
    const c = document.createElement("canvas");
    c.width = 900;
    c.height = 260;
    const ctx = c.getContext("2d")!;
    ctx.fillStyle = ink;
    ctx.textBaseline = "middle";
    let size = 150;
    do {
      ctx.font = `${size}px 'Segoe Script', 'Brush Script MT', 'Snell Roundhand', cursive`;
      size -= 6;
    } while (ctx.measureText(typed).width > 860 && size > 30);
    ctx.fillText(typed, 20, 130);
    onChange(trim(c));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [typed, ink, mode]);

  const point = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    return [((e.clientX - rect.left) / rect.width) * e.currentTarget.width, ((e.clientY - rect.top) / rect.height) * e.currentTarget.height];
  };

  const clear = () => {
    const ctx = canvas.current?.getContext("2d");
    ctx?.clearRect(0, 0, canvas.current!.width, canvas.current!.height);
    dirty.current = false;
    onChange("");
  };

  return (
    <div className="card p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {(
          [
            ["draw", PenLine, "Draw"],
            ["type", Type, "Type"],
            ["upload", Upload, "Upload"],
          ] as const
        ).map(([m, Icon, label]) => (
          <button key={m} type="button" onClick={() => setMode(m)} className={mode === m ? "btn-primary px-3 py-1.5" : "btn-secondary px-3 py-1.5"}>
            <Icon className="h-4 w-4" /> {label}
          </button>
        ))}
        {mode !== "upload" && (
          <div className="ml-auto flex gap-1.5" aria-label="Ink colour">
            {INKS.map((c) => (
              <button
                key={c}
                type="button"
                aria-label={`Ink ${c}`}
                onClick={() => setInk(c)}
                className={`h-6 w-6 rounded-full border-2 ${ink === c ? "border-brand-500" : "border-transparent"}`}
                style={{ background: c }}
              />
            ))}
          </div>
        )}
      </div>
      {mode === "draw" && (
        <div>
          <canvas
            ref={canvas}
            width={900}
            height={260}
            className="h-40 w-full touch-none rounded-lg border border-dashed border-slate-300 bg-white"
            onPointerDown={(e) => {
              drawing.current = true;
              const ctx = e.currentTarget.getContext("2d")!;
              const [x, y] = point(e);
              ctx.beginPath();
              ctx.moveTo(x, y);
              e.currentTarget.setPointerCapture(e.pointerId);
            }}
            onPointerMove={(e) => {
              if (!drawing.current) return;
              const ctx = e.currentTarget.getContext("2d")!;
              const [x, y] = point(e);
              ctx.lineWidth = 6;
              ctx.lineCap = "round";
              ctx.lineJoin = "round";
              ctx.strokeStyle = ink;
              ctx.lineTo(x, y);
              ctx.stroke();
              dirty.current = true;
            }}
            onPointerUp={() => {
              drawing.current = false;
              if (dirty.current && canvas.current) onChange(trim(canvas.current));
            }}
          />
          <button type="button" className="btn-ghost mt-2 px-3 py-1.5" onClick={clear}>
            <Eraser className="h-4 w-4" /> Clear
          </button>
        </div>
      )}
      {mode === "type" && (
        <input className="input font-signature text-3xl" placeholder="Type your name" value={typed} onChange={(e) => setTyped(e.target.value)} style={{ color: ink }} />
      )}
      {mode === "upload" && (
        <input
          type="file"
          accept="image/png,image/jpeg"
          className="input"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (!f) return;
            const reader = new FileReader();
            reader.onload = () => onChange(String(reader.result));
            reader.readAsDataURL(f);
          }}
        />
      )}
      {value && (
        <div className="mt-3 flex items-center gap-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={value} alt="Your signature" className="h-12 rounded border border-slate-200 bg-white p-1" />
          <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={clear}>
            <Trash2 className="h-3.5 w-3.5" /> Remove
          </button>
        </div>
      )}
    </div>
  );
}

/** Crop transparent margins so the placed signature box hugs the ink. */
function trim(source: HTMLCanvasElement): string {
  const ctx = source.getContext("2d")!;
  const { width, height } = source;
  const data = ctx.getImageData(0, 0, width, height).data;
  let minX = width, minY = height, maxX = -1, maxY = -1;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (data[(y * width + x) * 4 + 3] > 10) {
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      }
    }
  }
  if (maxX < 0) return "";
  const pad = 8;
  const out = document.createElement("canvas");
  out.width = maxX - minX + pad * 2;
  out.height = maxY - minY + pad * 2;
  out.getContext("2d")!.drawImage(source, minX - pad, minY - pad, out.width, out.height, 0, 0, out.width, out.height);
  return out.toDataURL("image/png");
}
