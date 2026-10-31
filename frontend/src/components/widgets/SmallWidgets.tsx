"use client";

import { BadgeCheck, Plus, Trash2 } from "lucide-react";

import type { OptionValues } from "../OptionsForm";

/** Optional image for watermarks, stored as a data URL. */
export function ImagePicker({ values, onChange }: { values: OptionValues; onChange: (v: OptionValues) => void }) {
  const image = values.image as string | null | undefined;
  return (
    <div>
      <span className="label">Image watermark (optional)</span>
      {image ? (
        <div className="flex items-center gap-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={image} alt="Watermark" className="h-14 rounded border border-slate-200 bg-white p-1" />
          <button className="btn-ghost px-2 py-1" onClick={() => onChange({ ...values, image: null })}>
            <Trash2 className="h-4 w-4" /> Use text instead
          </button>
        </div>
      ) : (
        <input
          type="file"
          accept="image/png,image/jpeg"
          className="input"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (!f) return;
            const reader = new FileReader();
            reader.onload = () => onChange({ ...values, image: String(reader.result) });
            reader.readAsDataURL(f);
          }}
        />
      )}
    </div>
  );
}

type Mark = { title: string; page: number; level: number };

export function BookmarksEditor({ values, onChange }: { values: OptionValues; onChange: (v: OptionValues) => void }) {
  const marks = (values.bookmarks as Mark[] | undefined) ?? [{ title: "", page: 1, level: 0 }];
  const set = (next: Mark[]) => onChange({ ...values, bookmarks: next });
  return (
    <div>
      <span className="label">Bookmarks</span>
      <div className="space-y-2">
        {marks.map((m, i) => (
          <div key={i} className="flex gap-2" style={{ paddingLeft: m.level * 16 }}>
            <input className="input" placeholder="Title" value={m.title} onChange={(e) => set(marks.map((x, k) => (k === i ? { ...x, title: e.target.value } : x)))} />
            <input className="input w-24" type="number" min={1} aria-label="Page" value={m.page} onChange={(e) => set(marks.map((x, k) => (k === i ? { ...x, page: Number(e.target.value) } : x)))} />
            <select className="input w-28" aria-label="Level" value={m.level} onChange={(e) => set(marks.map((x, k) => (k === i ? { ...x, level: Number(e.target.value) } : x)))}>
              <option value={0}>Top</option>
              <option value={1}>Nested</option>
              <option value={2}>Nested ×2</option>
            </select>
            <button className="btn-ghost px-2" aria-label="Remove" onClick={() => set(marks.filter((_, k) => k !== i))}>
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
      <button className="btn-secondary mt-2 px-3 py-1.5" onClick={() => set([...marks, { title: "", page: (marks.at(-1)?.page ?? 0) + 1, level: 0 }])}>
        <Plus className="h-4 w-4" /> Add bookmark
      </button>
    </div>
  );
}

/** Certificate file (.p12 / .pfx) for digital signatures, kept as a data URL. Leaving it empty creates one. */
export function CertificatePicker({ values, onChange }: { values: OptionValues; onChange: (v: OptionValues) => void }) {
  const cert = values.certificate as string | null | undefined;
  const name = values._certificate_name as string | undefined;
  return (
    <div>
      <span className="label">Certificate</span>
      {cert ? (
        <div className="flex items-center justify-between gap-2 rounded-xl border border-slate-200 p-2 text-sm dark:border-slate-700">
          <span className="flex min-w-0 items-center gap-2">
            <BadgeCheck className="h-4 w-4 shrink-0 text-emerald-600" />
            <span className="truncate">{name ?? "Certificate loaded"}</span>
          </span>
          <button className="btn-ghost px-2 py-1" onClick={() => onChange({ ...values, certificate: null, certificate_password: null, _certificate_name: undefined })}>
            <Trash2 className="h-4 w-4" /> Remove
          </button>
        </div>
      ) : (
        <>
          <input
            type="file"
            accept=".p12,.pfx,application/x-pkcs12"
            className="input"
            aria-label="Certificate file"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              const reader = new FileReader();
              reader.onload = () => onChange({ ...values, certificate: String(reader.result), _certificate_name: f.name });
              reader.readAsDataURL(f);
            }}
          />
          <p className="help">Use your own .p12 or .pfx file, or leave this empty and we&apos;ll make a personal certificate for you.</p>
        </>
      )}
    </div>
  );
}
