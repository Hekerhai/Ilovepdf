"use client";

import { ChevronDown, CircleDot, type LucideIcon, MousePointer2, Signature, SquareCheck, TextCursorInput, Trash2, Type } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import type { FieldSpec } from "@/lib/engines/browser-handlers";

import type { OptionValues } from "../OptionsForm";
import { clamp, dragBox, fractionAt, PageStage, usePdfPage } from "./stage";

type Kind = FieldSpec["type"];
type Drag = { mode: "create" | "move" | "resize"; index: number; origin: [number, number]; start: FieldSpec };

const KINDS: { id: Kind; label: string; icon: LucideIcon; size: [number, number] }[] = [
  { id: "text", label: "Text box", icon: TextCursorInput, size: [180, 22] },
  { id: "multiline", label: "Paragraph", icon: Type, size: [260, 70] },
  { id: "checkbox", label: "Checkbox", icon: SquareCheck, size: [14, 14] },
  { id: "dropdown", label: "Dropdown", icon: ChevronDown, size: [160, 22] },
  { id: "radio", label: "Radio buttons", icon: CircleDot, size: [140, 44] },
  { id: "signature", label: "Signature", icon: Signature, size: [180, 50] },
];

/** Draw fillable fields onto a PDF: text boxes, checkboxes, dropdowns, radio buttons and signature fields. */
export function FormBuilder({ file, values, onChange }: { file: File; values: OptionValues; onChange: (v: OptionValues) => void }) {
  const fields = (values.fields as FieldSpec[] | undefined) ?? [];
  const [page, setPage] = useState(1);
  const { view, count, error } = usePdfPage(file, page);
  const [kind, setKind] = useState<Kind | "select">("text");
  const [selected, setSelected] = useState<number | null>(null);
  const drag = useRef<Drag | null>(null);
  const stage = useRef<HTMLDivElement>(null);
  const W = view?.width ?? 612;
  const H = view?.height ?? 792;

  const latest = useRef(values);
  latest.current = values;
  const setFields = useCallback((next: FieldSpec[]) => onChange({ ...latest.current, fields: next }), [onChange]);
  const update = (i: number, patch: Partial<FieldSpec>) => setFields(fields.map((f, k) => (k === i ? { ...f, ...patch } : f)));
  const remove = useCallback(
    (i: number) => {
      setFields(fields.filter((_, k) => k !== i));
      setSelected(null);
    },
    [fields, setFields],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement) return;
      if ((e.key === "Delete" || e.key === "Backspace") && selected !== null) {
        e.preventDefault();
        remove(selected);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected, remove]);

  function uniqueName(type: Kind) {
    const base = type === "multiline" ? "notes" : type;
    let n = fields.filter((f) => f.type === type).length + 1;
    while (fields.some((f) => f.name === `${base}_${n}`)) n++;
    return `${base}_${n}`;
  }

  function down(e: React.PointerEvent<HTMLDivElement>) {
    if (!stage.current || e.button > 0) return;
    if (kind === "select") return setSelected(null);
    const [fx, fy] = fractionAt(e, stage.current);
    stage.current.setPointerCapture(e.pointerId);
    const field: FieldSpec = {
      type: kind,
      name: uniqueName(kind),
      page,
      x: clamp(fx),
      y: clamp(fy),
      width: 0,
      height: 0,
      options: kind === "dropdown" || kind === "radio" ? ["Option 1", "Option 2"] : [],
      required: false,
    };
    setFields([...fields, field]);
    setSelected(fields.length);
    drag.current = { mode: "create", index: fields.length, origin: [fx, fy], start: field };
  }

  function move(e: React.PointerEvent<HTMLDivElement>) {
    const d = drag.current;
    if (!d || !stage.current) return;
    const [fx, fy] = fractionAt(e, stage.current);
    if (d.mode === "create") {
      const [ox, oy] = d.origin;
      update(d.index, { x: clamp(Math.min(ox, fx)), y: clamp(Math.min(oy, fy)), width: Math.abs(fx - ox), height: Math.abs(fy - oy) });
    } else {
      update(d.index, dragBox(d.start, d.mode, fx - d.origin[0], fy - d.origin[1]));
    }
  }

  function up() {
    const d = drag.current;
    drag.current = null;
    if (!d || d.mode !== "create") return;
    const f = fields[d.index];
    if (f && (f.width * W < 8 || f.height * H < 8)) {
      const [w, h] = KINDS.find((k) => k.id === f.type)!.size;
      update(d.index, { width: Math.min(w / W, 1 - f.x), height: Math.min(h / H, 1 - f.y) });
    }
    setKind("select");
  }

  function startDrag(e: React.PointerEvent, i: number, mode: "move" | "resize") {
    if (kind !== "select" || !stage.current) return;
    e.stopPropagation();
    stage.current.setPointerCapture(e.pointerId);
    setSelected(i);
    drag.current = { mode, index: i, origin: fractionAt(e, stage.current), start: fields[i] };
  }

  const sel = selected !== null ? fields[selected] : null;
  const duplicate = sel ? fields.some((f, i) => i !== selected && f.name === sel.name) : false;

  return (
    <div className="space-y-3">
      <div className="card flex flex-wrap items-center gap-1 p-2" role="toolbar" aria-label="Field types">
        <ToolButton active={kind === "select"} label="Select and move" icon={MousePointer2} onClick={() => setKind("select")} />
        {KINDS.map((k) => (
          <ToolButton key={k.id} active={kind === k.id} label={k.label} icon={k.icon} onClick={() => setKind(k.id)} showLabel />
        ))}
      </div>

      {error && <p className="text-sm text-rose-600">{error}</p>}
      <PageStage
        view={view}
        page={page}
        count={count}
        onPage={(p) => (setPage(p), setSelected(null))}
        footer={<span className="text-xs text-slate-500">{fields.length ? `${fields.length} field${fields.length > 1 ? "s" : ""}` : "Pick a field type, then drag a box on the page."}</span>}
      >
        <div
          ref={stage}
          className={`relative h-full w-full touch-none ${kind === "select" ? "" : "cursor-crosshair"}`}
          onPointerDown={down}
          onPointerMove={move}
          onPointerUp={up}
          onPointerCancel={up}
          data-testid="form-canvas"
        >
          {fields.map((f, i) =>
            f.page === page ? (
              <div
                key={i}
                onPointerDown={(e) => startDrag(e, i, "move")}
                className={`absolute flex items-center overflow-hidden rounded-sm border text-[10px] font-medium leading-none ${
                  selected === i ? "border-brand-600 bg-brand-500/20 ring-2 ring-brand-500/40" : "border-sky-500 bg-sky-400/15"
                } ${kind === "select" ? "cursor-move" : "pointer-events-none"}`}
                style={{ left: `${f.x * 100}%`, top: `${f.y * 100}%`, width: `${f.width * 100}%`, height: `${f.height * 100}%` }}
              >
                <span className="truncate px-1 text-sky-900 dark:text-sky-100">{f.type === "checkbox" ? "" : f.type === "radio" ? (f.options ?? []).join(" / ") : f.name}</span>
                {selected === i && (
                  <span onPointerDown={(e) => startDrag(e, i, "resize")} className="absolute bottom-0 right-0 h-2.5 w-2.5 cursor-nwse-resize bg-brand-600" aria-label="Resize" />
                )}
              </div>
            ) : null,
          )}
        </div>
      </PageStage>
      {/* Field settings sit below the page: anything appearing above it would shift the page under the pointer. */}
      {sel && (
        <div className="card grid gap-3 p-3 text-sm sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-500">Field name</span>
            <input className={`input py-1 ${duplicate ? "border-rose-400" : ""}`} value={sel.name} onChange={(e) => update(selected!, { name: e.target.value.replace(/\s+/g, "_") })} />
            {duplicate && <span className="text-xs text-rose-600">Another field already has this name.</span>}
          </label>
          {(sel.type === "dropdown" || sel.type === "radio") && (
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-500">Choices (comma separated)</span>
              <input
                className="input py-1"
                value={(sel.options ?? []).join(", ")}
                onChange={(e) => update(selected!, { options: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })}
              />
            </label>
          )}
          {(sel.type === "text" || sel.type === "multiline" || sel.type === "dropdown") && (
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-500">Pre-filled value</span>
              <input className="input py-1" value={sel.default ?? ""} onChange={(e) => update(selected!, { default: e.target.value || null })} />
            </label>
          )}
          <div className="flex items-end justify-between gap-3">
            {sel.type !== "signature" && (
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={Boolean(sel.required)} onChange={(e) => update(selected!, { required: e.target.checked })} /> Required
              </label>
            )}
            <button type="button" className="btn-ghost px-2 py-1 text-rose-600" onClick={() => remove(selected!)}>
              <Trash2 className="h-4 w-4" /> Remove field
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function ToolButton({ active, label, icon: Icon, onClick, showLabel }: { active: boolean; label: string; icon: LucideIcon; onClick: () => void; showLabel?: boolean }) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={active}
      onClick={onClick}
      className={`flex items-center gap-1.5 rounded-lg px-2 py-2 text-sm transition ${active ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"}`}
    >
      <Icon className="h-4 w-4" />
      {showLabel && <span className="hidden sm:inline">{label}</span>}
    </button>
  );
}
