"use client";

import {
  Bold,
  Circle,
  Eraser,
  Highlighter,
  ImagePlus,
  Italic,
  type LucideIcon,
  Minus,
  MousePointer2,
  MoveUpRight,
  Pencil,
  Square,
  Trash2,
  Type,
  Undo2,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import type { EditObject } from "@/lib/engines/browser-handlers";

import type { OptionValues } from "../OptionsForm";
import { type BoxLike, clamp, dragBox, fractionAt, PageStage, readDataUrl, usePdfPage } from "./stage";

type Tool = "select" | EditObject["type"];
type Drag =
  | { mode: "create"; index: number; origin: [number, number] }
  | { mode: "draw"; index: number }
  | { mode: "move" | "resize"; index: number; origin: [number, number]; start: EditObject };

const TOOLS: { id: Tool; label: string; icon: LucideIcon }[] = [
  { id: "select", label: "Select and move", icon: MousePointer2 },
  { id: "text", label: "Text", icon: Type },
  { id: "image", label: "Image", icon: ImagePlus },
  { id: "rect", label: "Rectangle", icon: Square },
  { id: "ellipse", label: "Ellipse", icon: Circle },
  { id: "line", label: "Line", icon: Minus },
  { id: "arrow", label: "Arrow", icon: MoveUpRight },
  { id: "highlight", label: "Highlight", icon: Highlighter },
  { id: "whiteout", label: "White out", icon: Eraser },
  { id: "draw", label: "Draw", icon: Pencil },
];

const FAMILIES = { sans: "Helvetica, Arial, sans-serif", serif: "'Times New Roman', Times, serif", mono: "'Courier New', Courier, monospace" };
// Must match ASCENT / LINE_HEIGHT in the browser handlers and backend/app/tools/editor.py.
const ASCENT = 0.8;
const LINE_HEIGHT = 1.2;
const BOX_TYPES = new Set(["image", "rect", "ellipse", "highlight", "whiteout"]);

type Style = Pick<EditObject, "color" | "fill" | "stroke_width" | "opacity" | "font" | "font_size" | "bold" | "italic">;
const DEFAULT_STYLE: Style = { color: "#111827", fill: null, stroke_width: 2, opacity: 1, font: "sans", font_size: 16, bold: false, italic: false };

let measureCtx: CanvasRenderingContext2D | null = null;
function textBox(o: EditObject, W: number, H: number): BoxLike {
  measureCtx ??= document.createElement("canvas").getContext("2d");
  const size = o.font_size ?? 14;
  const lines = (o.text ?? "").split("\n");
  let width = size;
  if (measureCtx) {
    measureCtx.font = `${o.italic ? "italic " : ""}${o.bold ? "bold " : ""}${size}px ${FAMILIES[o.font ?? "sans"]}`;
    width = Math.max(size, ...lines.map((l) => measureCtx!.measureText(l).width));
  }
  return { x: o.x, y: o.y, width: width / W, height: (lines.length * size * LINE_HEIGHT) / H };
}

function bounds(o: EditObject, W: number, H: number): BoxLike {
  if (o.type === "text") return textBox(o, W, H);
  if (o.type === "line" || o.type === "arrow") {
    const x2 = o.x2 ?? o.x;
    const y2 = o.y2 ?? o.y;
    return { x: Math.min(o.x, x2), y: Math.min(o.y, y2), width: Math.abs(x2 - o.x), height: Math.abs(y2 - o.y) };
  }
  if (o.type === "draw") {
    const xs = (o.points ?? []).map((p) => p[0]);
    const ys = (o.points ?? []).map((p) => p[1]);
    return { x: Math.min(...xs), y: Math.min(...ys), width: Math.max(...xs) - Math.min(...xs), height: Math.max(...ys) - Math.min(...ys) };
  }
  return { x: o.x, y: o.y, width: o.width ?? 0, height: o.height ?? 0 };
}

function moved(start: EditObject, dx: number, dy: number): EditObject {
  if (start.type === "draw") return { ...start, points: (start.points ?? []).map(([px, py]) => [px + dx, py + dy] as [number, number]) };
  const next = { ...start, x: start.x + dx, y: start.y + dy };
  if (start.type === "line" || start.type === "arrow") return { ...next, x2: (start.x2 ?? 0) + dx, y2: (start.y2 ?? 0) + dy };
  if (BOX_TYPES.has(start.type)) return { ...next, ...dragBox(start as BoxLike, "move", dx, dy) };
  return next;
}

/** A visual PDF editor: add text, images, shapes, highlights, white-out and freehand drawing to any page. */
export function PdfEditor({ file, values, onChange }: { file: File; values: OptionValues; onChange: (v: OptionValues) => void }) {
  const objects = (values.objects as EditObject[] | undefined) ?? [];
  const [page, setPage] = useState(1);
  const { view, count, error } = usePdfPage(file, page);
  const [tool, setTool] = useState<Tool>("select");
  const [selected, setSelected] = useState<number | null>(null);
  const [style, setStyle] = useState<Style>(DEFAULT_STYLE);
  const [editing, setEditing] = useState(false);
  const drag = useRef<Drag | null>(null);
  const history = useRef<EditObject[][]>([]);
  const svg = useRef<SVGSVGElement>(null);
  const imageInput = useRef<HTMLInputElement>(null);
  const textInput = useRef<HTMLTextAreaElement>(null);
  const W = view?.width ?? 612;
  const H = view?.height ?? 792;

  const latest = useRef(values);
  latest.current = values;
  const setObjects = useCallback(
    (next: EditObject[], remember = true) => {
      if (remember) history.current = [...history.current.slice(-49), (latest.current.objects as EditObject[] | undefined) ?? []];
      onChange({ ...latest.current, objects: next });
    },
    [onChange],
  );
  const update = (index: number, patch: Partial<EditObject>, remember = true) =>
    setObjects(objects.map((o, i) => (i === index ? { ...o, ...patch } : o)), remember);
  const remove = useCallback(
    (index: number) => {
      setObjects(objects.filter((_, i) => i !== index));
      setSelected(null);
    },
    [objects, setObjects],
  );
  const undo = () => {
    const prev = history.current.pop();
    if (prev) onChange({ ...latest.current, objects: prev });
    setSelected(null);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement;
      if (typing) return;
      if ((e.key === "Delete" || e.key === "Backspace") && selected !== null) {
        e.preventDefault();
        remove(selected);
      }
      if (e.key === "Escape") setSelected(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected, remove]);

  const sel = selected !== null ? objects[selected] : null;
  const current: Style = sel ? { ...DEFAULT_STYLE, ...sel } : style;
  const setStyleValue = (patch: Partial<Style>) => {
    setStyle({ ...style, ...patch });
    if (selected !== null) update(selected, patch);
  };

  function pointerDown(e: React.PointerEvent<SVGSVGElement>) {
    if (!svg.current || e.button > 0) return;
    const [fx, fy] = fractionAt(e, svg.current);
    if (tool === "select") {
      setSelected(null);
      setEditing(false);
      return;
    }
    if (tool === "image") {
      imageInput.current?.click();
      return;
    }
    svg.current.setPointerCapture(e.pointerId);
    const base = { page, x: fx, y: fy, color: style.color, opacity: style.opacity, stroke_width: style.stroke_width };
    let obj: EditObject;
    if (tool === "text") {
      obj = { ...base, type: "text", text: "Type here", font: style.font, font_size: style.font_size, bold: style.bold, italic: style.italic, y: fy - ((style.font_size ?? 16) * 0.6) / H };
      setObjects([...objects, obj]);
      setSelected(objects.length);
      setEditing(true);
      setTool("select");
      setTimeout(() => textInput.current?.select(), 0);
      return;
    }
    if (tool === "draw") obj = { ...base, type: "draw", x: 0, y: 0, points: [[fx, fy]] };
    else if (tool === "line" || tool === "arrow") obj = { ...base, type: tool, x2: fx, y2: fy };
    else obj = { ...base, type: tool, width: 0, height: 0, fill: tool === "rect" || tool === "ellipse" ? style.fill : null };
    setObjects([...objects, obj]);
    setSelected(objects.length);
    drag.current = tool === "draw" ? { mode: "draw", index: objects.length } : { mode: "create", index: objects.length, origin: [fx, fy] };
  }

  function pointerMove(e: React.PointerEvent<SVGSVGElement>) {
    const d = drag.current;
    if (!d || !svg.current) return;
    const [fx, fy] = fractionAt(e, svg.current);
    const obj = objects[d.index];
    if (!obj) return;
    if (d.mode === "draw") {
      const last = obj.points?.at(-1);
      if (last && Math.hypot(fx - last[0], fy - last[1]) < 0.002) return;
      update(d.index, { points: [...(obj.points ?? []), [clamp(fx), clamp(fy)]] }, false);
    } else if (d.mode === "create") {
      if (obj.type === "line" || obj.type === "arrow") update(d.index, { x2: fx, y2: fy }, false);
      else {
        const [ox, oy] = d.origin;
        update(d.index, { x: Math.min(ox, fx), y: Math.min(oy, fy), width: Math.abs(fx - ox), height: Math.abs(fy - oy) }, false);
      }
    } else {
      const dx = fx - d.origin[0];
      const dy = fy - d.origin[1];
      if (d.mode === "move") update(d.index, moved(d.start, dx, dy), false);
      else if (d.start.type === "text") update(d.index, { font_size: Math.max(4, Math.round((d.start.font_size ?? 14) * (1 + (dy * H) / ((d.start.font_size ?? 14) * 3)))) }, false);
      else {
        const next = dragBox(d.start as BoxLike, "resize", dx, dy);
        if (d.start.type === "image" && d.start.width) next.height = (next.width * (d.start.height ?? 0)) / d.start.width;
        update(d.index, next, false);
      }
    }
  }

  function pointerUp() {
    const d = drag.current;
    drag.current = null;
    if (!d || d.mode !== "create") return;
    const obj = objects[d.index];
    if (!obj) return;
    if (obj.type === "line" || obj.type === "arrow") {
      if (Math.hypot((obj.x2 ?? 0) - obj.x, (obj.y2 ?? 0) - obj.y) < 0.01) update(d.index, { x2: obj.x + 0.2, y2: obj.y }, false);
    } else if ((obj.width ?? 0) < 0.01 || (obj.height ?? 0) < 0.005) {
      const size = obj.type === "highlight" ? [0.25, 0.022] : obj.type === "whiteout" ? [0.2, 0.04] : [0.2, 0.08];
      update(d.index, { width: size[0], height: size[1] }, false);
    }
    setTool("select");
  }

  function startDrag(e: React.PointerEvent, index: number, mode: "move" | "resize") {
    if (tool !== "select" || !svg.current) return;
    e.stopPropagation();
    svg.current.setPointerCapture(e.pointerId);
    history.current = [...history.current.slice(-49), objects];
    if (index !== selected) setEditing(false);
    setSelected(index);
    drag.current = { mode, index, origin: fractionAt(e, svg.current), start: objects[index] };
  }

  async function addImage(f: File | undefined) {
    if (!f) return;
    const src = await readDataUrl(f);
    const img = new Image();
    img.onload = () => {
      const width = 0.3;
      const height = (width * W * (img.naturalHeight / img.naturalWidth)) / H;
      setObjects([...objects, { type: "image", page, x: 0.35, y: 0.35, width, height, image: src, opacity: 1 }]);
      setSelected(objects.length);
      setTool("select");
    };
    img.src = src;
  }

  const onPage = objects.map((o, i) => [o, i] as const).filter(([o]) => o.page === page);
  const selBox = sel && sel.page === page ? bounds(sel, W, H) : null;
  const showFill = sel ? sel.type === "rect" || sel.type === "ellipse" : tool === "rect" || tool === "ellipse";
  const showText = sel ? sel.type === "text" : tool === "text";
  const showStroke = sel ? ["rect", "ellipse", "line", "arrow", "draw"].includes(sel.type) : ["rect", "ellipse", "line", "arrow", "draw"].includes(tool);

  return (
    <div className="space-y-3">
      <div className="card flex flex-wrap items-center gap-1 p-2" role="toolbar" aria-label="Editing tools">
        {TOOLS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            title={label}
            aria-label={label}
            aria-pressed={tool === id}
            onClick={() => {
              setTool(id);
              if (id === "image") imageInput.current?.click();
            }}
            className={`rounded-lg p-2 transition ${tool === id ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"}`}
          >
            <Icon className="h-4 w-4" />
          </button>
        ))}
        <span className="mx-1 h-6 w-px bg-slate-200 dark:bg-slate-700" />
        <button type="button" className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 disabled:opacity-40 dark:text-slate-300" title="Undo" aria-label="Undo" disabled={!history.current.length} onClick={undo}>
          <Undo2 className="h-4 w-4" />
        </button>
        <button type="button" className="rounded-lg p-2 text-rose-600 hover:bg-rose-50 disabled:opacity-40" title="Delete" aria-label="Delete selected" disabled={selected === null} onClick={() => selected !== null && remove(selected)}>
          <Trash2 className="h-4 w-4" />
        </button>
        <input ref={imageInput} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={(e) => (addImage(e.target.files?.[0]), (e.target.value = ""))} />
      </div>

      {/* One fixed-height row: anything that changes the height above the page would shift it under the pointer mid-drag. */}
      <div className="card flex items-end gap-3 overflow-x-auto whitespace-nowrap p-3 text-sm">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-slate-500">Colour</span>
          <input type="color" aria-label="Colour" className="h-8 w-10 cursor-pointer rounded border border-slate-300" value={current.color ?? "#111827"} onChange={(e) => setStyleValue({ color: e.target.value })} />
        </label>
        {showFill && (
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-500">Fill</span>
            <span className="flex items-center gap-1">
              <input type="checkbox" aria-label="Fill shape" checked={Boolean(current.fill)} onChange={(e) => setStyleValue({ fill: e.target.checked ? current.fill || "#bfdbfe" : null })} />
              {current.fill && <input type="color" aria-label="Fill colour" className="h-8 w-10 cursor-pointer rounded border border-slate-300" value={current.fill} onChange={(e) => setStyleValue({ fill: e.target.value })} />}
            </span>
          </label>
        )}
        {showStroke && (
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-500">Thickness</span>
            <input type="range" min={0} max={12} step={0.5} value={current.stroke_width ?? 2} onChange={(e) => setStyleValue({ stroke_width: Number(e.target.value) })} />
          </label>
        )}
        {showText && (
          <>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-500">Font</span>
              <select className="input py-1" value={current.font} onChange={(e) => setStyleValue({ font: e.target.value as Style["font"] })}>
                <option value="sans">Sans</option>
                <option value="serif">Serif</option>
                <option value="mono">Mono</option>
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-500">Size</span>
              <input type="number" className="input w-20 py-1" min={4} max={200} value={current.font_size} onChange={(e) => setStyleValue({ font_size: Math.max(4, Number(e.target.value) || 4) })} />
            </label>
            <button type="button" aria-label="Bold" aria-pressed={current.bold} className={`rounded-lg p-2 ${current.bold ? "bg-slate-200 dark:bg-slate-700" : ""}`} onClick={() => setStyleValue({ bold: !current.bold })}>
              <Bold className="h-4 w-4" />
            </button>
            <button type="button" aria-label="Italic" aria-pressed={current.italic} className={`rounded-lg p-2 ${current.italic ? "bg-slate-200 dark:bg-slate-700" : ""}`} onClick={() => setStyleValue({ italic: !current.italic })}>
              <Italic className="h-4 w-4" />
            </button>
          </>
        )}
        <label className="flex flex-col gap-1">
          <span className="text-xs text-slate-500">Opacity</span>
          <input type="range" min={0.1} max={1} step={0.05} value={current.opacity ?? 1} onChange={(e) => setStyleValue({ opacity: Number(e.target.value) })} />
        </label>
      </div>

      {error && <p className="text-sm text-rose-600">{error}</p>}
      <PageStage
        view={view}
        page={page}
        count={count}
        onPage={(p) => (setPage(p), setSelected(null), setEditing(false))}
        footer={
          <span className="text-xs text-slate-500">
            {objects.length ? `${objects.length} change${objects.length > 1 ? "s" : ""} · double-click text to edit it` : "Pick a tool, then click or drag on the page."}
          </span>
        }
      >
        <svg
          ref={svg}
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          className={`h-full w-full touch-none ${tool === "select" ? "cursor-default" : "cursor-crosshair"}`}
          onPointerDown={pointerDown}
          onPointerMove={pointerMove}
          onPointerUp={pointerUp}
          onPointerCancel={pointerUp}
          data-testid="editor-canvas"
        >
          {onPage.map(([o, i]) => (
            <g key={i} style={{ pointerEvents: tool === "select" ? "all" : "none", cursor: "move" }} onPointerDown={(e) => startDrag(e, i, "move")} onDoubleClick={() => o.type === "text" && (setEditing(true), setTimeout(() => textInput.current?.focus(), 0))}>
              {!(editing && i === selected) && <Shape o={o} W={W} H={H} />}
            </g>
          ))}
          {selBox && selected !== null && (
            <g>
              <rect x={selBox.x * W - 3} y={selBox.y * H - 3} width={selBox.width * W + 6} height={selBox.height * H + 6} fill="none" stroke="#4f46e5" strokeDasharray="4 3" strokeWidth={1} pointerEvents="none" />
              {(BOX_TYPES.has(sel!.type) || sel!.type === "text") && (
                <rect
                  x={(selBox.x + selBox.width) * W - 1}
                  y={(selBox.y + selBox.height) * H - 1}
                  width={8}
                  height={8}
                  fill="#4f46e5"
                  className="cursor-nwse-resize"
                  onPointerDown={(e) => startDrag(e, selected, "resize")}
                  aria-label="Resize"
                />
              )}
            </g>
          )}
        </svg>
        {editing && sel?.type === "text" && sel.page === page && (
          <div className="pointer-events-none absolute inset-0" style={{ containerType: "inline-size" }}>
            <textarea
              ref={textInput}
              aria-label="Text"
              value={sel.text ?? ""}
              onChange={(e) => update(selected!, { text: e.target.value }, false)}
              onBlur={() => setEditing(false)}
              rows={(sel.text ?? "").split("\n").length}
              className="pointer-events-auto absolute resize-none overflow-hidden border border-dashed border-brand-500 bg-white/70 p-0 outline-none"
              style={{
                left: `${sel.x * 100}%`,
                top: `${sel.y * 100}%`,
                minWidth: `${Math.max(textBox(sel, W, H).width * 100 + 2, 12)}%`,
                fontSize: `${((sel.font_size ?? 14) / W) * 100}cqw`,
                lineHeight: LINE_HEIGHT,
                fontFamily: FAMILIES[sel.font ?? "sans"],
                fontWeight: sel.bold ? 700 : 400,
                fontStyle: sel.italic ? "italic" : "normal",
                color: sel.color ?? "#111827",
              }}
            />
          </div>
        )}
      </PageStage>
    </div>
  );
}

function Shape({ o, W, H }: { o: EditObject; W: number; H: number }) {
  const x = o.x * W;
  const y = o.y * H;
  const w = (o.width ?? 0) * W;
  const h = (o.height ?? 0) * H;
  const stroke = o.color ?? "#111827";
  const sw = o.stroke_width ?? 2;
  const common = { opacity: o.opacity ?? 1 };
  switch (o.type) {
    case "text": {
      const size = o.font_size ?? 14;
      return (
        <text x={x} y={y + size * ASCENT} fontSize={size} fontFamily={FAMILIES[o.font ?? "sans"]} fontWeight={o.bold ? 700 : 400} fontStyle={o.italic ? "italic" : "normal"} fill={stroke} {...common} style={{ whiteSpace: "pre" }}>
          {(o.text ?? "").split("\n").map((line, i) => (
            <tspan key={i} x={x} dy={i ? size * LINE_HEIGHT : 0}>
              {line || " "}
            </tspan>
          ))}
        </text>
      );
    }
    case "image":
      return <image href={o.image ?? ""} x={x} y={y} width={w} height={h} preserveAspectRatio="none" {...common} />;
    case "rect":
      return <rect x={x} y={y} width={w} height={h} fill={o.fill ?? "transparent"} stroke={sw > 0 ? stroke : "none"} strokeWidth={sw} {...common} />;
    case "ellipse":
      return <ellipse cx={x + w / 2} cy={y + h / 2} rx={w / 2} ry={h / 2} fill={o.fill ?? "transparent"} stroke={sw > 0 ? stroke : "none"} strokeWidth={sw} {...common} />;
    case "highlight":
      return <rect x={x} y={y} width={w} height={h} fill={o.fill || "#FDE047"} opacity={Math.min(o.opacity ?? 1, 0.4)} />;
    case "whiteout":
      return <rect x={x} y={y} width={w} height={h} fill={o.fill || "#FFFFFF"} stroke="#cbd5e1" strokeDasharray="2 2" strokeWidth={0.5} {...common} />;
    case "line":
    case "arrow": {
      const x2 = (o.x2 ?? o.x) * W;
      const y2 = (o.y2 ?? o.y) * H;
      const head = Math.max(8, sw * 4);
      const angle = Math.atan2(y2 - y, x2 - x);
      const wings = [-1, 1].map((side) => {
        const a = angle + Math.PI + (side * Math.PI) / 7;
        return `M${x2} ${y2} L${x2 + head * Math.cos(a)} ${y2 + head * Math.sin(a)}`;
      });
      return (
        <g stroke={stroke} strokeWidth={sw} strokeLinecap="round" {...common}>
          <line x1={x} y1={y} x2={x2} y2={y2} />
          {o.type === "arrow" && <path d={wings.join(" ")} fill="none" />}
          <line x1={x} y1={y} x2={x2} y2={y2} stroke="transparent" strokeWidth={Math.max(12, sw)} />
        </g>
      );
    }
    case "draw":
      return (
        <polyline
          points={(o.points ?? []).map(([px, py]) => `${px * W},${py * H}`).join(" ")}
          fill="none"
          stroke={stroke}
          strokeWidth={sw}
          strokeLinecap="round"
          strokeLinejoin="round"
          {...common}
        />
      );
  }
}
