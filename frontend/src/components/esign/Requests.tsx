"use client";

import { Bell, CheckCircle2, Clock, Download, FileSignature, Plus, ShieldCheck, Trash2, XCircle } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useSession } from "@/components/AppProviders";
import { esign, type RequestDetail as Detail, type RequestStatus, type RequestSummary, type SignerStatus, signerColour } from "@/lib/esign";

const STATUS: Record<RequestStatus, { label: string; className: string }> = {
  sent: { label: "Waiting for signatures", className: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200" },
  completed: { label: "Completed", className: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200" },
  declined: { label: "Declined", className: "bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-200" },
  cancelled: { label: "Cancelled", className: "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300" },
  expired: { label: "Expired", className: "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300" },
};
const SIGNER: Record<SignerStatus, string> = { waiting: "Not yet sent", pending: "Sent", viewed: "Opened", signed: "Signed", declined: "Declined" };
const EVENTS: Record<string, string> = {
  created: "Sent for signature",
  viewed: "Opened the document",
  signed: "Signed",
  declined: "Declined",
  reminded: "Reminder sent",
  cancelled: "Cancelled",
  expired: "Expired",
  completed: "Completed and sealed",
};

const date = (iso: string) => new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

function Badge({ status }: { status: RequestStatus }) {
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS[status].className}`}>{STATUS[status].label}</span>;
}

function SignInFirst({ next }: { next: string }) {
  return (
    <div className="container-page py-16 text-center">
      <FileSignature className="mx-auto mb-3 h-10 w-10 text-brand-600" />
      <h1 className="mb-2 text-2xl font-semibold">Request signatures</h1>
      <p className="mx-auto mb-6 max-w-md text-slate-600 dark:text-slate-400">
        Send a PDF to one or more people, track who has signed, and get a sealed copy with an audit trail when everyone is done. Free accounts include 3 requests a month.
      </p>
      <Link href={`/login?next=${encodeURIComponent(next)}`} className="btn-primary">
        Sign in to send a request
      </Link>
    </div>
  );
}

export function RequestList() {
  const { user, plan, loading } = useSession();
  const [rows, setRows] = useState<RequestSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (user) esign.list().then((r) => setRows(r.requests), (e) => setError(e.message));
  }, [user]);

  if (loading) return null;
  if (!user) return <SignInFirst next="/esign" />;
  const limit = plan?.esign_requests_per_month;
  const thisMonth = rows?.filter((r) => new Date(r.created_at).getMonth() === new Date().getMonth() && new Date(r.created_at).getFullYear() === new Date().getFullYear()).length ?? 0;

  return (
    <div className="container-page max-w-4xl py-10">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Signature requests</h1>
          {limit != null && (
            <p className="text-sm text-slate-500">
              {thisMonth} of {limit} used this month · <Link href="/pricing" className="underline">Unlimited on Pro</Link>
            </p>
          )}
        </div>
        <Link href="/esign/new" className="btn-primary">
          <Plus className="h-4 w-4" /> New request
        </Link>
      </div>
      {error && <p className="text-sm text-rose-600">{error}</p>}
      {rows && !rows.length && (
        <div className="card p-10 text-center text-slate-500">
          <FileSignature className="mx-auto mb-2 h-8 w-8" />
          Nothing sent yet. Start with <Link href="/esign/new" className="underline">a new request</Link>.
        </div>
      )}
      <ul className="space-y-2">
        {rows?.map((r) => (
          <li key={r.id}>
            <Link href={`/esign/${r.id}`} className="card flex flex-wrap items-center gap-3 p-4 transition hover:border-brand-400">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{r.title}</p>
                <p className="truncate text-sm text-slate-500">
                  {r.signers.filter((s) => s.status === "signed").length} of {r.signers.length} signed · sent {date(r.created_at)}
                </p>
              </div>
              <div className="flex -space-x-1">
                {r.signers.map((s, i) => (
                  <span key={i} title={`${s.name}: ${SIGNER[s.status]}`} className={`flex h-7 w-7 items-center justify-center rounded-full border-2 border-white text-xs font-semibold text-white dark:border-slate-900 ${s.status === "signed" ? "" : "opacity-40"}`} style={{ background: signerColour(i) }}>
                    {s.name.slice(0, 1).toUpperCase()}
                  </span>
                ))}
              </div>
              <Badge status={r.status} />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function RequestView({ id }: { id: string }) {
  const { user, loading } = useSession();
  const router = useRouter();
  const justSent = useSearchParams().get("sent") === "1";
  const [req, setReq] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(justSent ? "Sent. Everyone gets an email with their own link." : null);

  const load = useCallback(() => esign.get(id).then(setReq, (e) => setError(e.message)), [id]);
  useEffect(() => {
    if (user) load();
  }, [user, load]);

  const act = async (fn: () => Promise<unknown>, done: string) => {
    setError(null);
    try {
      const r = await fn();
      if (r && typeof r === "object" && "id" in r) setReq(r as Detail);
      setNote(done);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  if (loading) return null;
  if (!user) return <SignInFirst next={`/esign/${id}`} />;
  if (error && !req) return <div className="container-page py-16 text-center text-rose-600">{error}</div>;
  if (!req) return <div className="container-page py-16 text-center text-slate-500">Loading…</div>;

  const waiting = req.status === "sent";

  return (
    <div className="container-page max-w-4xl py-10">
      <Link href="/esign" className="text-sm text-slate-500 hover:underline">
        ← All requests
      </Link>
      <div className="mb-6 mt-2 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{req.title}</h1>
          <p className="text-sm text-slate-500">
            {req.file_name} · sent {date(req.created_at)}
            {waiting && ` · link expires ${date(req.expires_at)}`}
          </p>
        </div>
        <Badge status={req.status} />
      </div>
      {note && <p className="mb-4 rounded-lg bg-emerald-50 px-4 py-2 text-sm text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-200">{note}</p>}
      {error && <p className="mb-4 text-sm text-rose-600">{error}</p>}

      <div className="mb-6 flex flex-wrap gap-2">
        {!req.files_deleted && (
          <a href={esign.documentUrl(req.id)} target="_blank" rel="noreferrer" className={req.status === "completed" ? "btn-primary" : "btn-secondary"}>
            <Download className="h-4 w-4" /> {req.status === "completed" ? "Download signed copy" : "View document"}
          </a>
        )}
        {waiting && (
          <>
            <button type="button" className="btn-secondary" onClick={() => act(() => esign.remind(req.id), "Reminder sent with a fresh link.")}>
              <Bell className="h-4 w-4" /> Send reminder
            </button>
            <button type="button" className="btn-ghost" onClick={() => confirm("Cancel this request? Signers will be told.") && act(() => esign.cancel(req.id), "Request cancelled.")}>
              <XCircle className="h-4 w-4" /> Cancel request
            </button>
          </>
        )}
        <button
          type="button"
          className="btn-ghost text-rose-600"
          onClick={() => confirm("Delete this request and its documents? This can't be undone.") && esign.remove(req.id).then(() => router.push("/esign"), (e) => setError(e.message))}
        >
          <Trash2 className="h-4 w-4" /> Delete
        </button>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <section className="card p-4">
          <h2 className="mb-3 font-semibold">Signers{req.sequential && <span className="ml-2 text-xs font-normal text-slate-500">in order</span>}</h2>
          <ul className="space-y-3">
            {req.signers.map((s, i) => (
              <li key={i} className="flex items-start gap-3">
                <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white" style={{ background: signerColour(i) }}>
                  {s.name.slice(0, 1).toUpperCase()}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{s.name}</p>
                  <p className="truncate text-sm text-slate-500">{s.email}</p>
                  {s.decline_reason && <p className="mt-1 text-sm text-rose-600">“{s.decline_reason}”</p>}
                </div>
                <span className="flex items-center gap-1 text-sm">
                  {s.status === "signed" ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : s.status === "declined" ? <XCircle className="h-4 w-4 text-rose-600" /> : <Clock className="h-4 w-4 text-slate-400" />}
                  {SIGNER[s.status]}
                </span>
              </li>
            ))}
          </ul>
        </section>
        <section className="card p-4">
          <h2 className="mb-3 font-semibold">History</h2>
          <ol className="space-y-2 text-sm">
            {req.events.map((e, i) => (
              <li key={i} className="flex gap-3">
                <span className="w-36 shrink-0 text-slate-500">{date(e.at)}</span>
                <span>
                  {e.who && <b>{e.who} </b>}
                  {e.who ? EVENTS[e.kind]?.toLowerCase() ?? e.kind : EVENTS[e.kind] ?? e.kind}
                </span>
              </li>
            ))}
          </ol>
        </section>
      </div>
      {req.final_sha256 && (
        <p className="mt-6 flex items-start gap-2 text-sm text-slate-500">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
          <span>
            The signed copy is sealed with a digital signature and ends with a signature certificate page. SHA-256: <code className="break-all">{req.final_sha256}</code>. Documents are deleted 30 days after a request finishes.
          </span>
        </p>
      )}
    </div>
  );
}
