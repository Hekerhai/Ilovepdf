"use client";

import { ArrowDown, ArrowUp, X } from "lucide-react";
import { useState } from "react";

import { formatBytes } from "@/lib/format";

import { FileThumb } from "./FileThumb";

export function FileList({ files, onChange, ordered }: { files: File[]; onChange: (files: File[]) => void; ordered: boolean }) {
  const [dragging, setDragging] = useState<number | null>(null);

  const move = (from: number, to: number) => {
    if (to < 0 || to >= files.length || from === to) return;
    const next = [...files];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    onChange(next);
  };

  return (
    <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {files.map((file, i) => (
        <li
          key={`${file.name}-${file.size}-${file.lastModified}-${i}`}
          draggable={ordered}
          onDragStart={() => setDragging(i)}
          onDragOver={(e) => e.preventDefault()}
          onDrop={() => dragging !== null && (move(dragging, i), setDragging(null))}
          className={`card flex items-center gap-3 p-3 ${ordered ? "cursor-grab active:cursor-grabbing" : ""} ${dragging === i ? "opacity-50" : ""}`}
        >
          <FileThumb file={file} className="h-20 w-14" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium" title={file.name}>
              {ordered && <span className="mr-1 text-slate-400">{i + 1}.</span>}
              {file.name}
            </p>
            <p className="text-xs text-slate-500">{formatBytes(file.size)}</p>
          </div>
          <div className="flex flex-col gap-1">
            {ordered && (
              <>
                <button className="btn-ghost p-1" onClick={() => move(i, i - 1)} aria-label="Move up" disabled={i === 0}>
                  <ArrowUp className="h-4 w-4" />
                </button>
                <button className="btn-ghost p-1" onClick={() => move(i, i + 1)} aria-label="Move down" disabled={i === files.length - 1}>
                  <ArrowDown className="h-4 w-4" />
                </button>
              </>
            )}
          </div>
          <button className="btn-ghost p-1" onClick={() => onChange(files.filter((_, k) => k !== i))} aria-label={`Remove ${file.name}`}>
            <X className="h-4 w-4" />
          </button>
        </li>
      ))}
    </ul>
  );
}
