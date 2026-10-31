"use client";

import type { ReactNode } from "react";

import type { JsonSchema, ToolInfo } from "@/lib/types";

export type OptionValues = Record<string, unknown>;

/** Fields rendered by a dedicated widget (or not at all) instead of the generic form. */
export const CUSTOM_FIELDS: Record<string, string[]> = {
  sign: ["signature", "placements"],
  organize: ["pages"],
  watermark: ["image"],
  create_bookmarks: ["bookmarks"],
  redact: ["areas"],
  ai_chat: ["question", "history"],
  edit_pdf: ["objects"],
  annotate_pdf: ["objects"],
  fill_forms: ["fields"],
  create_forms: ["fields"],
  digital_sign: ["certificate"],
};

/** Show a field only when it matters for the other choices. */
const VISIBLE_WHEN: Record<string, Record<string, (o: OptionValues) => boolean>> = {
  split: {
    ranges: (o) => (o.mode ?? "ranges") === "ranges",
    merge_output: (o) => (o.mode ?? "ranges") === "ranges",
    every: (o) => o.mode === "every",
    max_size_mb: (o) => o.mode === "size",
  },
  watermark: {
    text: (o) => !o.image,
    font_size: (o) => !o.image,
    color: (o) => !o.image,
    image_scale: (o) => Boolean(o.image),
  },
  images_to_pdf: {
    orientation: (o) => (o.page_size ?? "fit") !== "fit",
  },
  scan_to_pdf: {
    orientation: (o) => (o.page_size ?? "A4") !== "fit",
  },
  digital_sign: {
    certificate_password: (o) => Boolean(o.certificate),
    signer_name: (o) => !o.certificate,
    signer_email: (o) => !o.certificate,
    page: (o) => o.visible !== false && !o.field_name,
    position: (o) => o.visible !== false && !o.field_name,
  },
};

const LABELS: Record<string, string> = {
  dpi: "Resolution (DPI)",
  max_size_mb: "Max size per file (MB)",
  every: "Pages per file",
  margin_mm: "Margin (mm)",
  top_mm: "Top (mm)",
  right_mm: "Right (mm)",
  bottom_mm: "Bottom (mm)",
  left_mm: "Left (mm)",
  n_up: "Pages per sheet",
  per_sheet: "Pages per sheet",
  min_size_px: "Skip images smaller than (px)",
  url: "Web page URL",
  pdfa: "PDF/A",
  part: "PDF/A part",
  black_white: "Black & white",
  signer_name: "Your name",
  signer_email: "Your email (optional)",
  certificate_password: "Certificate password",
  field_name: "Sign an existing field (optional)",
  timestamp_url: "Timestamp server (optional)",
  certify: "Certify (lock everything but form filling)",
  visible: "Show a signature stamp",
  name_after_match: "Name files after the matching line",
  regex: "Regular expression",
  split: "Split",
  start_at: "Start counting at",
};

const LANGUAGES: [string, string][] = [
  ["eng", "English"],
  ["spa", "Spanish"],
  ["fra", "French"],
  ["deu", "German"],
  ["por", "Portuguese"],
  ["ita", "Italian"],
  ["hin", "Hindi"],
];

function humanize(name: string): string {
  if (LABELS[name]) return LABELS[name];
  const s = name.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function resolve(schema: JsonSchema, root: JsonSchema): JsonSchema {
  if (schema.$ref) {
    const key = schema.$ref.split("/").pop()!;
    return { ...root.$defs?.[key], ...schema, $ref: undefined };
  }
  if (schema.allOf?.length === 1) return resolve({ ...schema.allOf[0], ...schema, allOf: undefined }, root);
  return schema;
}

/** Unwrap Optional[...] (anyOf [X, null]) into X plus a nullable flag. */
function unwrap(schema: JsonSchema, root: JsonSchema): { s: JsonSchema; nullable: boolean } {
  const r = resolve(schema, root);
  if (r.anyOf) {
    const nonNull = r.anyOf.filter((x) => x.type !== "null");
    if (nonNull.length === 1) return { s: { ...resolve(nonNull[0], root), description: r.description, default: r.default }, nullable: true };
  }
  return { s: r, nullable: false };
}

export function defaultOptions(tool: ToolInfo): OptionValues {
  const values: OptionValues = {};
  for (const [name, prop] of Object.entries(tool.options_schema.properties ?? {})) {
    if (prop.default !== undefined) values[name] = prop.default;
  }
  // Prefer the private, in-browser path for merge by default.
  if (tool.id === "merge") values.add_bookmarks = false;
  return values;
}

export function OptionsForm({
  tool,
  values,
  onChange,
}: {
  tool: ToolInfo;
  values: OptionValues;
  onChange: (values: OptionValues) => void;
}) {
  const root = tool.options_schema;
  const custom = new Set(CUSTOM_FIELDS[tool.id] ?? []);
  const fields = Object.entries(root.properties ?? {}).filter(([name]) => !custom.has(name));
  const visible = fields.filter(([name]) => VISIBLE_WHEN[tool.id]?.[name]?.(values) ?? true);
  if (!visible.length) return null;
  const set = (name: string, value: unknown) => onChange({ ...values, [name]: value });

  return (
    <div className="space-y-4">
      {visible.map(([name, raw]) => {
        const { s, nullable } = unwrap(raw, root);
        const required = root.required?.includes(name);
        return (
          <Field key={name} name={name} label={humanize(name)} help={s.description} required={required}>
            {renderInput(name, s, nullable, values[name], (v) => set(name, v))}
          </Field>
        );
      })}
    </div>
  );
}

function Field({ name, label, help, required, children }: { name: string; label: string; help?: string; required?: boolean; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={`opt-${name}`} className="label">
        {label}
        {required && <span className="text-rose-500"> *</span>}
      </label>
      {children}
      {help && <p className="help">{help}</p>}
    </div>
  );
}

function renderInput(name: string, s: JsonSchema, nullable: boolean, value: unknown, set: (v: unknown) => void): ReactNode {
  const id = `opt-${name}`;
  if (s.enum) {
    const options = s.enum;
    if (options.length <= 4) {
      return (
        <div className="flex flex-wrap gap-2" role="radiogroup" id={id}>
          {options.map((opt) => (
            <button
              type="button"
              key={String(opt)}
              role="radio"
              aria-checked={value === opt}
              onClick={() => set(opt)}
              className={`chip px-3 py-1.5 text-sm ${
                value === opt
                  ? "border-brand-600 bg-brand-600 text-white"
                  : "border-slate-200 bg-white text-slate-700 hover:border-brand-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
              }`}
            >
              {humanize(String(opt))}
            </button>
          ))}
        </div>
      );
    }
    return (
      <select id={id} className="input" value={String(value ?? "")} onChange={(e) => set(typeof options[0] === "number" ? Number(e.target.value) : e.target.value)}>
        {options.map((opt) => (
          <option key={String(opt)} value={String(opt)}>
            {humanize(String(opt))}
          </option>
        ))}
      </select>
    );
  }
  if (s.type === "boolean") {
    return (
      <button
        type="button"
        id={id}
        role="switch"
        aria-checked={Boolean(value)}
        onClick={() => set(!value)}
        className={`relative inline-flex h-6 w-11 items-center rounded-full transition ${value ? "bg-brand-600" : "bg-slate-300 dark:bg-slate-700"}`}
      >
        <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition ${value ? "translate-x-5" : "translate-x-0.5"}`} />
      </button>
    );
  }
  if (s.type === "integer" || s.type === "number") {
    return (
      <input
        id={id}
        type="number"
        className="input"
        value={value === undefined || value === null ? "" : String(value)}
        min={s.minimum ?? s.exclusiveMinimum}
        max={s.maximum}
        step={s.type === "integer" ? 1 : "any"}
        onChange={(e) => set(e.target.value === "" ? (nullable ? null : undefined) : Number(e.target.value))}
      />
    );
  }
  if (s.type === "array") {
    const item = s.items ?? {};
    const list = Array.isArray(value) ? (value as string[]) : [];
    if (name === "languages") {
      return <ChipSet id={id} options={LANGUAGES} selected={list} onChange={set} />;
    }
    if (item.enum) {
      return <ChipSet id={id} options={item.enum.map((e) => [String(e), humanize(String(e))])} selected={list} onChange={set} />;
    }
    return (
      <input
        id={id}
        className="input"
        placeholder="Separate entries with commas"
        value={list.join(", ")}
        onChange={(e) => set(e.target.value.split(",").map((x) => x.trim()).filter(Boolean))}
      />
    );
  }
  const text = value === undefined || value === null ? "" : String(value);
  if (name.includes("color")) {
    return (
      <div className="flex items-center gap-2">
        <input id={id} type="color" className="h-10 w-14 cursor-pointer rounded-lg border border-slate-300" value={text || "#000000"} onChange={(e) => set(e.target.value)} />
        <input className="input" value={text} onChange={(e) => set(e.target.value)} />
      </div>
    );
  }
  return (
    <input
      id={id}
      type={name.includes("password") ? "password" : name === "url" ? "url" : "text"}
      autoComplete={name.includes("password") ? "new-password" : "off"}
      className="input"
      value={text}
      maxLength={s.maxLength}
      onChange={(e) => set(e.target.value === "" && nullable ? null : e.target.value)}
    />
  );
}

function ChipSet({ id, options, selected, onChange }: { id: string; options: [string, string][]; selected: string[]; onChange: (v: string[]) => void }) {
  return (
    <div className="flex flex-wrap gap-2" id={id}>
      {options.map(([value, label]) => {
        const on = selected.includes(value);
        return (
          <button
            key={value}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(on ? selected.filter((x) => x !== value) : [...selected, value])}
            className={`chip px-3 py-1.5 text-sm ${
              on ? "border-brand-600 bg-brand-50 text-brand-700 dark:bg-brand-500/10 dark:text-brand-300" : "border-slate-200 bg-white text-slate-600 dark:border-slate-700 dark:bg-slate-900"
            }`}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}
