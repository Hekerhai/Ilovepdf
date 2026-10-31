"use client";

import { useEffect, useState } from "react";

import { type Box, fractionBox } from "@/lib/engines/geometry";

import type { OptionValues } from "../OptionsForm";
import { PageStage, usePdfPage } from "./stage";

type Kind = "text" | "multiline" | "checkbox" | "dropdown" | "radio" | "list" | "other";
type Widget = { page: number; box: Box; option?: string };
type FieldInfo = { name: string; kind: Kind; options: string[]; initial: string | boolean; readOnly: boolean; widgets: Widget[] };
type Answers = Record<string, string | boolean>;

/** Read a PDF's fields and where their boxes sit, entirely in the browser with pdf-lib. */
async function readFields(file: File): Promise<FieldInfo[]> {
  const lib = await import("pdf-lib");
  const doc = await lib.PDFDocument.load(await file.arrayBuffer());
  const pages = doc.getPages();
  const pageOf = new Map(pages.map((p, i) => [p.ref.toString(), i]));
  const out: FieldInfo[] = [];
  for (const field of doc.getForm().getFields()) {
    let kind: Kind = "other";
    let options: string[] = [];
    let initial: string | boolean = "";
    if (field instanceof lib.PDFTextField) {
      kind = field.isMultiline() ? "multiline" : "text";
      initial = field.getText() ?? "";
    } else if (field instanceof lib.PDFCheckBox) {
      kind = "checkbox";
      initial = field.isChecked();
    } else if (field instanceof lib.PDFDropdown) {
      kind = "dropdown";
      options = field.getOptions();
      initial = field.getSelected()[0] ?? "";
    } else if (field instanceof lib.PDFOptionList) {
      kind = "list";
      options = field.getOptions();
      initial = field.getSelected()[0] ?? "";
    } else if (field instanceof lib.PDFRadioGroup) {
      kind = "radio";
      options = field.getOptions();
      initial = field.getSelected() ?? "";
    }
    const widgets: Widget[] = [];
    field.acroField.getWidgets().forEach((w, k) => {
      const ref = w.P();
      let index = ref ? pageOf.get(ref.toString()) : undefined;
      if (index === undefined) {
        const own = doc.context.getObjectRef(w.dict);
        index = pages.findIndex((p) => p.node.Annots()?.asArray().some((a) => own && a.toString() === own.toString()));
      }
      if (index === undefined || index < 0) return;
      const page = pages[index];
      const box = fractionBox(page.getRotation().angle, page.getCropBox(), w.getRectangle());
      widgets.push({ page: index + 1, box, option: kind === "radio" ? options[k] : undefined });
    });
    out.push({ name: field.getName(), kind, options, initial, readOnly: field.isReadOnly(), widgets });
  }
  return out;
}

/** Fill in a PDF form right on the page. Only the answers you change are sent to the tool. */
export function FormFiller({ file, values, onChange }: { file: File; values: OptionValues; onChange: (v: OptionValues) => void }) {
  const answers = (values.fields as Answers | undefined) ?? {};
  const [fields, setFields] = useState<FieldInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const { view, count, error: viewError } = usePdfPage(file, page);

  useEffect(() => {
    let cancelled = false;
    setFields(null);
    setError(null);
    readFields(file)
      .then((f) => !cancelled && setFields(f))
      .catch(() => !cancelled && setError("Couldn't read this PDF's form. It may be password protected."));
    return () => {
      cancelled = true;
    };
  }, [file]);

  const valueOf = (f: FieldInfo) => (f.name in answers ? answers[f.name] : f.initial);
  const set = (name: string, value: string | boolean) => onChange({ ...values, fields: { ...answers, [name]: value } });

  if (error) return <p className="text-sm text-rose-600">{error}</p>;
  if (fields && !fields.length) {
    return (
      <div className="card p-6 text-center text-sm">
        <p className="font-medium">This PDF has no fillable fields.</p>
        <p className="mt-1 text-slate-500">
          Use <a className="underline" href="/tools/create_forms">Create forms</a> to add some, or <a className="underline" href="/tools/edit_pdf">Edit PDF</a> to type anywhere on the page.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {viewError && <p className="text-sm text-rose-600">{viewError}</p>}
      <PageStage view={view} page={page} count={count} onPage={setPage} footer={fields ? <span className="text-xs text-slate-500">{fields.length} fields · type straight onto the page</span> : null}>
        <div className="relative h-full w-full" style={{ containerType: "size" }}>
          {fields?.flatMap((f) =>
            f.widgets
              .filter((w) => w.page === page)
              .map((w, k) => <OnPageInput key={`${f.name}-${k}`} field={f} widget={w} value={valueOf(f)} onChange={(v) => set(f.name, v)} />),
          )}
        </div>
      </PageStage>

      {fields && (
        <details className="card p-4" open={fields.every((f) => !f.widgets.length)}>
          <summary className="cursor-pointer text-sm font-semibold">All fields ({fields.length})</summary>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {fields.map((f) => (
              <label key={f.name} className="flex flex-col gap-1 text-sm">
                <span className="text-xs text-slate-500">{f.name}</span>
                <ListInput field={f} value={valueOf(f)} onChange={(v) => set(f.name, v)} />
              </label>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function OnPageInput({ field, widget, value, onChange }: { field: FieldInfo; widget: Widget; value: string | boolean; onChange: (v: string | boolean) => void }) {
  const { box } = widget;
  const style = {
    left: `${box.x * 100}%`,
    top: `${box.y * 100}%`,
    width: `${box.width * 100}%`,
    height: `${box.height * 100}%`,
    fontSize: `min(${Math.max(box.height * 100 * 0.62, 1.2)}cqh, 1.4cqh + 6px)`,
  };
  const base = "absolute rounded-sm border border-sky-400/70 bg-sky-100/40 text-slate-900 outline-none focus:border-brand-600 focus:bg-white/80 focus:ring-2 focus:ring-brand-500/40";
  const label = `${field.name}${widget.option ? `: ${widget.option}` : ""}`;
  if (field.readOnly) return <div className="absolute" style={style} title={`${field.name} (read only)`} />;
  if (field.kind === "checkbox") {
    return (
      <button type="button" role="checkbox" aria-checked={value === true} aria-label={label} className={`${base} flex items-center justify-center font-bold`} style={style} onClick={() => onChange(!(value === true))}>
        {value === true ? "✓" : ""}
      </button>
    );
  }
  if (field.kind === "radio") {
    const on = value === widget.option;
    return (
      <button type="button" role="radio" aria-checked={on} aria-label={label} className={`${base} flex items-center justify-center rounded-full`} style={style} onClick={() => widget.option && onChange(widget.option)}>
        {on && <span className="h-1/2 w-1/2 rounded-full bg-slate-900" />}
      </button>
    );
  }
  if (field.kind === "dropdown" || field.kind === "list") {
    return (
      <select aria-label={label} className={`${base} px-0.5`} style={style} value={String(value)} onChange={(e) => onChange(e.target.value)}>
        <option value="" />
        {field.options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    );
  }
  if (field.kind === "multiline") {
    return <textarea aria-label={label} className={`${base} resize-none px-1`} style={style} value={String(value)} onChange={(e) => onChange(e.target.value)} />;
  }
  if (field.kind === "text") {
    return <input aria-label={label} className={`${base} px-1`} style={style} value={String(value)} onChange={(e) => onChange(e.target.value)} />;
  }
  return null;
}

function ListInput({ field, value, onChange }: { field: FieldInfo; value: string | boolean; onChange: (v: string | boolean) => void }) {
  if (field.kind === "checkbox") {
    return (
      <span className="flex items-center gap-2">
        <input type="checkbox" checked={value === true} disabled={field.readOnly} onChange={(e) => onChange(e.target.checked)} /> {value === true ? "Ticked" : "Not ticked"}
      </span>
    );
  }
  if (field.options.length) {
    return (
      <select className="input py-1" value={String(value)} disabled={field.readOnly} onChange={(e) => onChange(e.target.value)}>
        <option value="" />
        {field.options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    );
  }
  if (field.kind === "multiline") return <textarea className="input" rows={2} value={String(value)} disabled={field.readOnly} onChange={(e) => onChange(e.target.value)} />;
  if (field.kind === "text") return <input className="input py-1" value={String(value)} disabled={field.readOnly} onChange={(e) => onChange(e.target.value)} />;
  return <span className="text-xs text-slate-500">This field type can't be filled here.</span>;
}
