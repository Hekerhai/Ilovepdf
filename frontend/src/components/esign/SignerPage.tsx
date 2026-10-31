"use client";

import { CheckCircle2, Download, FileSignature, PenLine, X, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { SignaturePad } from "@/components/widgets/SignWidget";
import { PageStage, usePdfPage } from "@/components/widgets/stage";
import { esign, FIELD_LABELS, type SignerView } from "@/lib/esign";

type Adopting = "signature" | "initials" | null;

/** What someone sees when they open their signing link. No account needed: the link is the credential. */
export function SignerPage({ token }: { token: string }) {
  const [view, setView] = useState<SignerView | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [values, setValues] = useState<Record<string, string | boolean>>({});
  const [signature, setSignature] = useState("");
  const [initials, setInitials] = useState("");
  const [adopting, setAdopting] = useState<Adopting>(null);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [declining, setDeclining] = useState(false);
  const [reason, setReason] = useState("");
  const [done, setDone] = useState<"signed" | "declined" | null>(null);

  useEffect(() => {
    esign.view(token).then(
      (v) => {
        setView(v);
        if (v.signer.status !== "waiting") esign.signerDocument(token, v.request.file_name).then(setFile, (e) => setError(e.message));
      },
      (e) => setError(e.message),
    );
  }, [token]);

  const { view: pageView, count } = usePdfPage(file ?? undefined, page);
  const fields = useMemo(() => view?.fields.map((f, i) => ({ ...f, key: String(i) })) ?? [], [view]);
  const today = new Date().toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });

  const missing = fields.filter((f) => {
    if (f.type === "signature") return !signature;
    if (f.type === "initials") return !(initials || signature);
    if (f.type === "text") return f.required && !String(values[f.key] ?? "").trim();
    if (f.type === "checkbox") return f.required && values[f.key] !== true;
    return false;
  });

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      await esign.sign(token, { values, signature: signature || null, initials: initials || null, consent });
      setDone("signed");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function decline() {
    setBusy(true);
    try {
      await esign.decline(token, reason);
      setDone("declined");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (error && !view) return <Message icon={<XCircle className="h-10 w-10 text-rose-500" />} title="This link can't be opened" text={error} />;
  if (!view) return <div className="container-page py-16 text-center text-slate-500">Loading…</div>;
  if (done === "signed")
    return <Message icon={<CheckCircle2 className="h-10 w-10 text-emerald-600" />} title="Thanks, you've signed" text={`${view.request.sender} has been told. When everyone has signed, you'll get an email and can download the sealed copy from this same link.`} />;
  if (done === "declined") return <Message icon={<XCircle className="h-10 w-10 text-slate-500" />} title="You declined to sign" text={`${view.request.sender} has been told.`} />;
  if (view.signer.status === "waiting") return <Message icon={<FileSignature className="h-10 w-10 text-brand-600" />} title="It isn't your turn yet" text="Someone before you still needs to sign. You'll get an email when it's your turn." />;

  if (!view.can_sign) {
    const text =
      view.request.status === "completed"
        ? "Everyone has signed. You can download the sealed copy."
        : view.signer.status === "signed"
          ? "You've already signed. You'll get an email when everyone has."
          : `This request is ${view.request.status}.`;
    return (
      <Message icon={<CheckCircle2 className="h-10 w-10 text-emerald-600" />} title={view.request.title} text={text}>
        {view.final_available && (
          <a href={esign.signerDocumentUrl(token)} className="btn-primary mt-4" target="_blank" rel="noreferrer">
            <Download className="h-4 w-4" /> Download signed copy
          </a>
        )}
      </Message>
    );
  }

  return (
    <div className="container-page max-w-5xl py-8">
      <div className="mb-4">
        <p className="text-sm text-slate-500">{view.request.sender} asked you to sign</p>
        <h1 className="text-2xl font-semibold">{view.request.title}</h1>
        {view.request.message && <p className="mt-2 whitespace-pre-line rounded-lg bg-slate-100 px-4 py-3 text-sm dark:bg-slate-800">{view.request.message}</p>}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
        <div>
          <PageStage view={pageView} page={page} count={count} onPage={setPage}>
            <div className="absolute inset-0 [container-type:inline-size]">
            {fields
              .filter((f) => f.page === page)
              .map((f) => {
                const box = { left: `${f.x * 100}%`, top: `${f.y * 100}%`, width: `${f.width * 100}%`, height: `${f.height * 100}%` };
                const empty = missing.includes(f);
                const outline = empty ? "border-amber-500 bg-amber-300/30" : "border-emerald-500 bg-emerald-300/10";
                if (f.type === "signature" || f.type === "initials") {
                  const image = f.type === "signature" ? signature : initials || signature;
                  return (
                    <button key={f.key} type="button" onClick={() => setAdopting(f.type as Adopting)} className={`absolute flex items-center justify-center rounded-sm border-2 border-dashed ${outline}`} style={box} aria-label={FIELD_LABELS[f.type]}>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      {image ? <img src={image} alt="" className="h-full w-full object-contain object-left" /> : <span className="flex items-center gap-1 text-xs font-medium text-amber-900"><PenLine className="h-3.5 w-3.5" /> {FIELD_LABELS[f.type]}</span>}
                    </button>
                  );
                }
                if (f.type === "text")
                  return (
                    <input key={f.key} aria-label={f.label || "Text"} placeholder={f.label || ""} value={String(values[f.key] ?? "")} onChange={(e) => setValues({ ...values, [f.key]: e.target.value })} className={`absolute rounded-sm border px-1 text-[clamp(8px,1.4cqw,14px)] text-slate-900 outline-none ${outline}`} style={box} />
                  );
                if (f.type === "checkbox")
                  return (
                    <input key={f.key} type="checkbox" aria-label={f.label || "Checkbox"} title={f.label ?? undefined} checked={values[f.key] === true} onChange={(e) => setValues({ ...values, [f.key]: e.target.checked })} className="absolute m-0 accent-brand-600" style={box} />
                  );
                return (
                  <span key={f.key} className="absolute flex items-center overflow-hidden whitespace-nowrap rounded-sm border border-slate-300 bg-slate-100/70 px-1 text-[clamp(8px,1.4cqw,14px)] text-slate-700" style={box}>
                    {f.type === "date" ? today : view.signer.name}
                  </span>
                );
              })}
            </div>
          </PageStage>
        </div>

        <aside className="space-y-4">
          <div className="card space-y-3 p-4 text-sm">
            <p className="font-medium">
              Signing as {view.signer.name}
              <span className="block font-normal text-slate-500">{view.signer.email}</span>
            </p>
            <ul className="space-y-1">
              {fields.map((f) => (
                <li key={f.key}>
                  <button type="button" className="flex w-full items-center gap-2 text-left hover:underline" onClick={() => (setPage(f.page), (f.type === "signature" || f.type === "initials") && setAdopting(f.type as Adopting))}>
                    {missing.includes(f) ? <span className="h-2 w-2 rounded-full bg-amber-500" /> : <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />}
                    {f.label || FIELD_LABELS[f.type]} <span className="ml-auto text-xs text-slate-400">p. {f.page}</span>
                  </button>
                </li>
              ))}
            </ul>
            <label className="flex items-start gap-2 border-t border-slate-200 pt-3 dark:border-slate-800">
              <input type="checkbox" className="mt-0.5" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
              <span>I agree to sign this document electronically, and that my electronic signature is as valid as a handwritten one.</span>
            </label>
            {error && <p className="text-rose-600">{error}</p>}
            <button type="button" className="btn-primary w-full" disabled={busy || !consent || missing.length > 0} onClick={submit}>
              {busy ? "Signing…" : missing.length ? `${missing.length} field${missing.length > 1 ? "s" : ""} left` : "Finish signing"}
            </button>
          </div>
          <div className="text-sm">
            {declining ? (
              <div className="card space-y-2 p-4">
                <textarea className="input" rows={3} placeholder="Reason (optional, shared with the sender)" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} />
                <div className="flex justify-end gap-2">
                  <button type="button" className="btn-ghost px-3 py-1.5" onClick={() => setDeclining(false)}>
                    Back
                  </button>
                  <button type="button" className="btn-secondary px-3 py-1.5 text-rose-600" disabled={busy} onClick={decline}>
                    Decline to sign
                  </button>
                </div>
              </div>
            ) : (
              <button type="button" className="text-slate-500 underline" onClick={() => setDeclining(true)}>
                Decline to sign
              </button>
            )}
          </div>
        </aside>
      </div>

      {adopting && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal aria-label={`Your ${adopting}`}>
          <div className="w-full max-w-xl rounded-2xl bg-white p-4 shadow-xl dark:bg-slate-900">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="font-semibold">{adopting === "signature" ? "Your signature" : "Your initials"}</h2>
              <button type="button" className="btn-ghost px-2 py-1" aria-label="Close" onClick={() => setAdopting(null)}>
                <X className="h-4 w-4" />
              </button>
            </div>
            <SignaturePad value={adopting === "signature" ? signature : initials} onChange={adopting === "signature" ? setSignature : setInitials} />
            <div className="mt-3 flex justify-end">
              <button type="button" className="btn-primary" disabled={adopting === "signature" ? !signature : !initials} onClick={() => setAdopting(null)}>
                Use this {adopting}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Message({ icon, title, text, children }: { icon: React.ReactNode; title: string; text: string; children?: React.ReactNode }) {
  return (
    <div className="container-page flex max-w-lg flex-col items-center py-20 text-center">
      {icon}
      <h1 className="mb-2 mt-3 text-2xl font-semibold">{title}</h1>
      <p className="text-slate-600 dark:text-slate-400">{text}</p>
      {children}
    </div>
  );
}
