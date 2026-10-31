"use client";

import { Calendar, CaseSensitive, Check, MousePointer2, PenLine, Plus, Send, SquareCheck, Trash2, Type, User } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { Dropzone } from "@/components/Dropzone";
import { clamp, dragBox, fractionAt, PageStage, usePdfPage } from "@/components/widgets/stage";
import { esign, FIELD_LABELS, type FieldType, type SignField, signerColour } from "@/lib/esign";

type Person = { name: string; email: string };
type Drag = { mode: "move" | "resize"; index: number; origin: [number, number]; start: SignField };

const TOOLS: { id: FieldType; icon: typeof PenLine; size: [number, number] }[] = [
  { id: "signature", icon: PenLine, size: [170, 48] },
  { id: "initials", icon: CaseSensitive, size: [60, 36] },
  { id: "date", icon: Calendar, size: [100, 18] },
  { id: "name", icon: User, size: [150, 18] },
  { id: "text", icon: Type, size: [150, 18] },
  { id: "checkbox", icon: SquareCheck, size: [14, 14] },
];
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Send a PDF out for signature: pick the file, add people, place their fields, send. */
export function SendWizard() {
  const router = useRouter();
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [message, setMessage] = useState("");
  const [people, setPeople] = useState<Person[]>([{ name: "", email: "" }]);
  const [sequential, setSequential] = useState(false);
  const [days, setDays] = useState(14);
  const [fields, setFields] = useState<SignField[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const peopleOk = people.length > 0 && people.every((p) => p.name.trim() && EMAIL.test(p.email.trim()));
  const duplicate = new Set(people.map((p) => p.email.trim().toLowerCase())).size !== people.length;
  const missingSignature = people.findIndex((_, i) => !fields.some((f) => f.signer === i && (f.type === "signature" || f.type === "initials")));

  async function send() {
    if (!file) return;
    setError(null);
    setSending(true);
    try {
      const sent = await esign.send(file, {
        title: title.trim() || file.name.replace(/\.pdf$/i, ""),
        message: message.trim(),
        signers: people.map((p) => ({ name: p.name.trim(), email: p.email.trim() })),
        fields,
        sequential,
        expires_in_days: days,
      });
      router.push(`/esign/${sent.id}?sent=1`);
    } catch (e) {
      setError((e as Error).message);
      setSending(false);
    }
  }

  return (
    <div className="container-page max-w-5xl py-10">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Request signatures</h1>
        <Link href="/esign" className="btn-ghost px-3 py-2 text-sm">
          All requests
        </Link>
      </div>
      <ol className="mb-6 flex gap-2 text-sm" aria-label="Steps">
        {["Document", "People", "Fields"].map((label, i) => (
          <li key={label} className={`flex items-center gap-2 rounded-full px-3 py-1 ${step === i + 1 ? "bg-brand-600 text-white" : step > i + 1 ? "bg-brand-100 text-brand-800 dark:bg-brand-900/40 dark:text-brand-200" : "bg-slate-100 text-slate-500 dark:bg-slate-800"}`}>
            {step > i + 1 ? <Check className="h-3.5 w-3.5" /> : <span>{i + 1}</span>} {label}
          </li>
        ))}
      </ol>

      {step === 1 && (
        <div className="space-y-4">
          <Dropzone
            accept={[".pdf"]}
            multiple={false}
            onFiles={(files) => {
              const f = files[0];
              if (!f) return;
              setFile(f);
              setFields([]);
              setTitle((t) => t || f.name.replace(/\.pdf$/i, ""));
              setStep(2);
            }}
          />
          <p className="text-center text-sm text-slate-500">Only you and the people you add can open the document. It is deleted 30 days after the request finishes.</p>
        </div>
      )}

      {step === 2 && (
        <div className="card space-y-5 p-5">
          <label className="block">
            <span className="text-sm font-medium">Title</span>
            <input className="input mt-1" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
          </label>
          <div>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-medium">Who needs to sign?</span>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={sequential} onChange={(e) => setSequential(e.target.checked)} /> Sign in this order
              </label>
            </div>
            <div className="space-y-2">
              {people.map((p, i) => (
                <div key={i} className="flex flex-wrap items-center gap-2">
                  <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: signerColour(i) }} aria-hidden />
                  {sequential && <span className="w-5 text-sm text-slate-500">{i + 1}.</span>}
                  <input className="input min-w-40 flex-1" placeholder="Name" aria-label={`Signer ${i + 1} name`} value={p.name} onChange={(e) => setPeople(people.map((q, k) => (k === i ? { ...q, name: e.target.value } : q)))} />
                  <input className="input min-w-52 flex-1" type="email" placeholder="Email" aria-label={`Signer ${i + 1} email`} value={p.email} onChange={(e) => setPeople(people.map((q, k) => (k === i ? { ...q, email: e.target.value } : q)))} />
                  <button
                    type="button"
                    className="btn-ghost px-2 py-2"
                    aria-label={`Remove signer ${i + 1}`}
                    disabled={people.length === 1}
                    onClick={() => {
                      setPeople(people.filter((_, k) => k !== i));
                      setFields(fields.filter((f) => f.signer !== i).map((f) => (f.signer > i ? { ...f, signer: f.signer - 1 } : f)));
                    }}
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
            {people.length < 20 && (
              <button type="button" className="btn-ghost mt-2 px-3 py-1.5 text-sm" onClick={() => setPeople([...people, { name: "", email: "" }])}>
                <Plus className="h-4 w-4" /> Add someone
              </button>
            )}
            {duplicate && <p className="mt-1 text-sm text-rose-600">Each person needs a different email address.</p>}
          </div>
          <label className="block">
            <span className="text-sm font-medium">Message (optional)</span>
            <textarea className="input mt-1" rows={3} value={message} onChange={(e) => setMessage(e.target.value)} maxLength={2000} placeholder="Hi, please sign this by Friday." />
          </label>
          <label className="flex items-center gap-2 text-sm">
            Link expires after
            <select className="input w-auto py-1" value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {[3, 7, 14, 30, 60, 90].map((d) => (
                <option key={d} value={d}>
                  {d} days
                </option>
              ))}
            </select>
          </label>
          <div className="flex justify-between">
            <button type="button" className="btn-ghost" onClick={() => setStep(1)}>
              Back
            </button>
            <button type="button" className="btn-primary" disabled={!peopleOk || duplicate} onClick={() => setStep(3)}>
              Next: place fields
            </button>
          </div>
        </div>
      )}

      {step === 3 && file && (
        <div className="space-y-4">
          <FieldPlacer file={file} people={people} fields={fields} onChange={setFields} />
          {error && <p className="text-sm text-rose-600">{error}</p>}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <button type="button" className="btn-ghost" onClick={() => setStep(2)}>
              Back
            </button>
            <div className="flex items-center gap-3">
              {missingSignature >= 0 && <span className="text-sm text-slate-500">Add a signature field for {people[missingSignature].name}.</span>}
              <button type="button" className="btn-primary" disabled={missingSignature >= 0 || sending} onClick={send}>
                <Send className="h-4 w-4" /> {sending ? "Sending…" : `Send to ${people.length} ${people.length > 1 ? "people" : "person"}`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function FieldPlacer({ file, people, fields, onChange }: { file: File; people: Person[]; fields: SignField[]; onChange: (f: SignField[]) => void }) {
  const [page, setPage] = useState(1);
  const { view, count, error } = usePdfPage(file, page);
  const [signer, setSigner] = useState(0);
  const [tool, setTool] = useState<FieldType | "select">("signature");
  const [selected, setSelected] = useState<number | null>(null);
  const stage = useRef<HTMLDivElement>(null);
  const drag = useRef<Drag | null>(null);
  const W = view?.width ?? 612;
  const H = view?.height ?? 792;

  const update = (i: number, patch: Partial<SignField>) => onChange(fields.map((f, k) => (k === i ? { ...f, ...patch } : f)));

  function place(e: React.PointerEvent<HTMLDivElement>) {
    if (!stage.current || tool === "select") return setSelected(null);
    const [fx, fy] = fractionAt(e, stage.current);
    const size = TOOLS.find((t) => t.id === tool)!.size;
    const width = Math.min(size[0] / W, 1);
    const height = Math.min(size[1] / H, 1);
    const field: SignField = {
      signer,
      type: tool,
      page,
      x: clamp(fx - width / 2, 0, 1 - width),
      y: clamp(fy - height / 2, 0, 1 - height),
      width,
      height,
      required: true,
      label: tool === "text" ? "Text" : tool === "checkbox" ? "I agree" : null,
    };
    onChange([...fields, field]);
    setSelected(fields.length);
  }

  function startDrag(e: React.PointerEvent, i: number, mode: "move" | "resize") {
    if (!stage.current) return;
    e.stopPropagation();
    stage.current.setPointerCapture(e.pointerId);
    setSelected(i);
    drag.current = { mode, index: i, origin: fractionAt(e, stage.current), start: fields[i] };
  }

  function move(e: React.PointerEvent) {
    const d = drag.current;
    if (!d || !stage.current) return;
    const [fx, fy] = fractionAt(e, stage.current);
    const b = dragBox(d.start, d.mode, fx - d.origin[0], fy - d.origin[1]);
    // Fields must stay on the page (the server checks this too).
    const width = Math.min(b.width, 1);
    const height = Math.min(b.height, 1);
    update(d.index, { width, height, x: clamp(b.x, 0, 1 - width), y: clamp(b.y, 0, 1 - height) });
  }

  const sel = selected !== null ? fields[selected] : null;

  return (
    <div className="grid gap-4 lg:grid-cols-[220px_1fr]">
      <aside className="card h-fit space-y-4 p-3 text-sm">
        <div>
          <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-500">Fields for</p>
          <div className="space-y-1">
            {people.map((p, i) => (
              <button
                key={i}
                type="button"
                onClick={() => setSigner(i)}
                aria-pressed={signer === i}
                className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left ${signer === i ? "bg-slate-100 font-medium dark:bg-slate-800" : "hover:bg-slate-50 dark:hover:bg-slate-900"}`}
              >
                <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: signerColour(i) }} />
                <span className="truncate">{p.name}</span>
                <span className="ml-auto text-xs text-slate-400">{fields.filter((f) => f.signer === i).length}</span>
              </button>
            ))}
          </div>
        </div>
        <div role="toolbar" aria-label="Field types">
          <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-500">Click the page to add</p>
          <div className="grid grid-cols-2 gap-1 lg:grid-cols-1">
            <button type="button" aria-pressed={tool === "select"} onClick={() => setTool("select")} className={`flex items-center gap-2 rounded-lg px-2 py-1.5 ${tool === "select" ? "bg-brand-600 text-white" : "hover:bg-slate-100 dark:hover:bg-slate-800"}`}>
              <MousePointer2 className="h-4 w-4" /> Select
            </button>
            {TOOLS.map((t) => (
              <button key={t.id} type="button" aria-pressed={tool === t.id} onClick={() => setTool(t.id)} className={`flex items-center gap-2 rounded-lg px-2 py-1.5 ${tool === t.id ? "bg-brand-600 text-white" : "hover:bg-slate-100 dark:hover:bg-slate-800"}`}>
                <t.icon className="h-4 w-4" /> {FIELD_LABELS[t.id]}
              </button>
            ))}
          </div>
        </div>
        {sel && (
          <div className="space-y-2 border-t border-slate-200 pt-3 dark:border-slate-800">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Selected field</p>
            <select className="input py-1" aria-label="Assigned to" value={sel.signer} onChange={(e) => update(selected!, { signer: Number(e.target.value) })}>
              {people.map((p, i) => (
                <option key={i} value={i}>
                  {p.name}
                </option>
              ))}
            </select>
            {(sel.type === "text" || sel.type === "checkbox") && (
              <>
                <input className="input py-1" aria-label="Field label" value={sel.label ?? ""} onChange={(e) => update(selected!, { label: e.target.value })} placeholder="Label shown to the signer" />
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={sel.required} onChange={(e) => update(selected!, { required: e.target.checked })} /> Required
                </label>
              </>
            )}
            <button
              type="button"
              className="btn-ghost w-full justify-start px-2 py-1 text-rose-600"
              onClick={() => {
                onChange(fields.filter((_, k) => k !== selected));
                setSelected(null);
              }}
            >
              <Trash2 className="h-4 w-4" /> Remove field
            </button>
          </div>
        )}
      </aside>
      <div>
        {error && <p className="text-sm text-rose-600">{error}</p>}
        <PageStage view={view} page={page} count={count} onPage={(p) => (setPage(p), setSelected(null))}>
          <div
            ref={stage}
            data-testid="esign-canvas"
            className={`relative h-full w-full touch-none ${tool === "select" ? "" : "cursor-copy"}`}
            onPointerDown={place}
            onPointerMove={move}
            onPointerUp={() => {
              drag.current = null;
            }}
          >
            {fields.map((f, i) =>
              f.page === page ? (
                <div
                  key={i}
                  onPointerDown={(e) => startDrag(e, i, "move")}
                  className={`absolute flex cursor-move items-center overflow-hidden rounded-sm border-2 px-1 text-[10px] font-medium ${selected === i ? "ring-2 ring-offset-1" : ""}`}
                  style={{
                    left: `${f.x * 100}%`,
                    top: `${f.y * 100}%`,
                    width: `${f.width * 100}%`,
                    height: `${f.height * 100}%`,
                    borderColor: signerColour(f.signer),
                    background: `${signerColour(f.signer)}22`,
                    color: signerColour(f.signer),
                  }}
                  title={`${FIELD_LABELS[f.type]} · ${people[f.signer]?.name}`}
                >
                  <span className="truncate">{f.type === "checkbox" ? "" : f.type === "text" ? f.label || "Text" : FIELD_LABELS[f.type]}</span>
                  {selected === i && <span onPointerDown={(e) => startDrag(e, i, "resize")} className="absolute bottom-0 right-0 h-2.5 w-2.5 cursor-nwse-resize" style={{ background: signerColour(f.signer) }} aria-label="Resize" />}
                </div>
              ) : null,
            )}
          </div>
        </PageStage>
      </div>
    </div>
  );
}
