"use client";

import { Camera, Upload } from "lucide-react";
import { useRef, useState } from "react";

import { ImportSources } from "@/components/ImportSources";

export function Dropzone({
  accept,
  multiple,
  onFiles,
  compact = false,
  allowCamera = false,
  allowImport = true,
}: {
  accept: string[];
  multiple: boolean;
  onFiles: (files: File[]) => void;
  compact?: boolean;
  allowCamera?: boolean;
  allowImport?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const camera = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  const accepted = (f: File) => accept.some((ext) => f.name.toLowerCase().endsWith(ext));
  const take = (list: FileList | null) => {
    const files = Array.from(list ?? []).filter(accepted);
    if (files.length) onFiles(multiple ? files : files.slice(0, 1));
  };

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        take(e.dataTransfer.files);
      }}
      className={`flex flex-col items-center justify-center rounded-2xl border-2 border-dashed text-center transition ${
        over ? "border-brand-500 bg-brand-50 dark:bg-brand-500/10" : "border-slate-300 bg-white dark:border-slate-700 dark:bg-slate-900"
      } ${compact ? "p-4" : "p-10 md:p-16"}`}
    >
      {!compact && <Upload className="mb-4 h-10 w-10 text-brand-500" />}
      <div className="flex flex-wrap justify-center gap-2">
        <button type="button" className={compact ? "btn-secondary" : "btn-primary px-8 py-4 text-base"} onClick={() => input.current?.click()}>
          {compact ? "Add more files" : `Select ${multiple ? "files" : "a file"}`}
        </button>
        {allowCamera && (
          <button type="button" className="btn-secondary" onClick={() => camera.current?.click()}>
            <Camera className="h-4 w-4" /> Scan with camera
          </button>
        )}
      </div>
      {!compact && <p className="mt-3 text-sm text-slate-500">or drop {accept.join(", ")} files here</p>}
      {!compact && allowImport && <ImportSources accept={accept} multiple={multiple} onFiles={onFiles} />}
      <input ref={input} type="file" hidden multiple={multiple} accept={accept.join(",")} onChange={(e) => (take(e.target.files), (e.target.value = ""))} />
      {allowCamera && (
        <input ref={camera} type="file" hidden accept="image/*" capture="environment" onChange={(e) => (take(e.target.files), (e.target.value = ""))} />
      )}
    </div>
  );
}
