"use client";

import { Copy, Download, Eye, FileText, Link2, Mail, Pencil, Search, Share2, Trash2, Upload, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { type Doc, documents, type Share } from "@/lib/documents";
import { formatBytes } from "@/lib/format";
import { catalog } from "@/lib/tools";

import { useSession } from "./AppProviders";

const QUICK_TOOLS = ["compress", "edit_pdf", "merge", "sign", "pdf_to_word", "ocr"];

/** Files the user chose to keep, with sharing. Results of tasks are deleted automatically; these are not. */
export function DocumentsView() {
  const { user, loading } = useSession();
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [usage, setUsage] = useState<{ used_bytes: number; limit_bytes: number } | null>(null);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sharing, setSharing] = useState<Doc | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const load = useCallback(
    () =>
      documents.list().then(
        (r) => (setDocs(r.documents), setUsage(r.usage)),
        (e) => setError(e.message),
      ),
    [],
  );
  useEffect(() => {
    if (user) load();
  }, [user, load]);

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    setError(null);
    try {
      await documents.upload(Array.from(files));
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  if (loading) return null;
  if (!user)
    return (
      <div className="container-page py-16 text-center">
        <FileText className="mx-auto mb-3 h-10 w-10 text-brand-600" />
        <h1 className="mb-2 text-2xl font-semibold">My documents</h1>
        <p className="mx-auto mb-6 max-w-md text-slate-600 dark:text-slate-400">Keep the files you want, share them with a link, and open them in any tool. Free accounts get 500 MB.</p>
        <Link href="/login?next=/documents" className="btn-primary">
          Sign in
        </Link>
      </div>
    );

  const shown = (docs ?? []).filter((d) => d.name.toLowerCase().includes(filter.toLowerCase()));
  const pct = usage && usage.limit_bytes ? Math.min(100, (usage.used_bytes / usage.limit_bytes) * 100) : 0;

  return (
    <div className="container-page max-w-5xl py-10">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">My documents</h1>
          {usage && (
            <div className="mt-2 w-64">
              <div className="h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
                <div className={`h-full ${pct > 90 ? "bg-rose-500" : "bg-brand-600"}`} style={{ width: `${pct}%` }} />
              </div>
              <p className="mt-1 text-xs text-slate-500">
                {formatBytes(usage.used_bytes)} of {formatBytes(usage.limit_bytes)} used
              </p>
            </div>
          )}
        </div>
        <div className="flex gap-2">
          <label className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
            <input className="input w-56 pl-8" placeholder="Search documents" aria-label="Search documents" value={filter} onChange={(e) => setFilter(e.target.value)} />
          </label>
          <button type="button" className="btn-primary" disabled={busy} onClick={() => input.current?.click()}>
            <Upload className="h-4 w-4" /> {busy ? "Uploading…" : "Upload"}
          </button>
          <input ref={input} type="file" multiple hidden aria-label="Upload documents" onChange={(e) => upload(e.target.files)} />
        </div>
      </div>
      {error && <p className="mb-4 text-sm text-rose-600">{error}</p>}
      {docs && !docs.length && (
        <div
          className="card p-12 text-center text-slate-500"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            upload(e.dataTransfer.files);
          }}
        >
          <FileText className="mx-auto mb-2 h-8 w-8" />
          Nothing here yet. Drop files here, or use <b>Save to My documents</b> after any tool.
        </div>
      )}
      {shown.length > 0 && (
        <div className="card divide-y divide-slate-200 dark:divide-slate-800">
          {shown.map((d) => (
            <div key={d.id} className="flex flex-wrap items-center gap-3 p-3">
              <FileText className="h-5 w-5 shrink-0 text-slate-400" />
              <div className="min-w-0 flex-1">
                {renaming === d.id ? (
                  <form
                    onSubmit={async (e) => {
                      e.preventDefault();
                      const name = new FormData(e.currentTarget).get("name") as string;
                      await documents.rename(d.id, name).catch((err) => setError(err.message));
                      setRenaming(null);
                      load();
                    }}
                  >
                    <input name="name" className="input py-1" defaultValue={d.name} autoFocus onBlur={() => setRenaming(null)} aria-label="New name" />
                  </form>
                ) : (
                  <p className="truncate font-medium">{d.name}</p>
                )}
                <p className="text-xs text-slate-500">
                  {formatBytes(d.size)} · {new Date(d.updated_at).toLocaleDateString()}
                </p>
              </div>
              {d.content_type === "application/pdf" && (
                <details className="relative">
                  <summary className="btn-ghost cursor-pointer list-none px-2 py-1 text-sm">Open in…</summary>
                  <div className="absolute right-0 z-10 mt-1 w-48 rounded-lg border border-slate-200 bg-white p-1 shadow-lg dark:border-slate-700 dark:bg-slate-900">
                    {QUICK_TOOLS.map((id) => {
                      const tool = catalog.tools.find((t) => t.id === id);
                      return tool ? (
                        <Link key={id} href={`/tools/${id}?document=${d.id}`} className="block rounded px-2 py-1.5 text-sm hover:bg-slate-100 dark:hover:bg-slate-800">
                          {tool.name}
                        </Link>
                      ) : null;
                    })}
                  </div>
                </details>
              )}
              <a className="btn-ghost px-2 py-1" href={documents.fileUrl(d.id)} target="_blank" rel="noreferrer" title="View" aria-label={`View ${d.name}`}>
                <Eye className="h-4 w-4" />
              </a>
              <a className="btn-ghost px-2 py-1" href={documents.fileUrl(d.id, true)} title="Download" aria-label={`Download ${d.name}`}>
                <Download className="h-4 w-4" />
              </a>
              <button type="button" className="btn-ghost px-2 py-1" title="Rename" aria-label={`Rename ${d.name}`} onClick={() => setRenaming(d.id)}>
                <Pencil className="h-4 w-4" />
              </button>
              <button type="button" className="btn-ghost px-2 py-1" title="Share" aria-label={`Share ${d.name}`} onClick={() => setSharing(d)}>
                <Share2 className="h-4 w-4" />
              </button>
              <button
                type="button"
                className="btn-ghost px-2 py-1 text-rose-600"
                title="Delete"
                aria-label={`Delete ${d.name}`}
                onClick={async () => {
                  if (!confirm(`Delete “${d.name}”? Its share links stop working.`)) return;
                  await documents.remove(d.id);
                  load();
                }}
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}
      {sharing && <ShareDialog doc={sharing} onClose={() => setSharing(null)} />}
    </div>
  );
}

export function ShareDialog({ doc, onClose }: { doc: Doc; onClose: () => void }) {
  const [shares, setShares] = useState<Share[]>([]);
  const [days, setDays] = useState<number | "">(7);
  const [password, setPassword] = useState("");
  const [maxDownloads, setMaxDownloads] = useState<number | "">("");
  const [allowDownload, setAllowDownload] = useState(true);
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => documents.shares(doc.id).then((r) => setShares(r.shares)), [doc.id]);
  useEffect(() => {
    load();
  }, [load]);

  const guard = async (fn: () => Promise<unknown>, done: string) => {
    setError(null);
    try {
      await fn();
      setNote(done);
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const copy = (text: string, what: string) => navigator.clipboard.writeText(text).then(() => setNote(`${what} copied.`));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal aria-label={`Share ${doc.name}`}>
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-5 shadow-xl dark:bg-slate-900">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="truncate font-semibold">Share “{doc.name}”</h2>
          <button type="button" className="btn-ghost px-2 py-1" aria-label="Close" onClick={onClose}>
            <X className="h-4 w-4" />
          </button>
        </div>
        <section className="space-y-3 text-sm">
          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-500">Expires after</span>
              <select className="input py-1" value={days} onChange={(e) => setDays(e.target.value ? Number(e.target.value) : "")}>
                {[1, 7, 30, 90].map((d) => (
                  <option key={d} value={d}>
                    {d} day{d > 1 ? "s" : ""}
                  </option>
                ))}
                <option value="">Never</option>
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-500">Download limit</span>
              <input className="input py-1" type="number" min={1} placeholder="No limit" value={maxDownloads} onChange={(e) => setMaxDownloads(e.target.value ? Number(e.target.value) : "")} />
            </label>
          </div>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-500">Password (optional)</span>
            <input className="input py-1" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="At least 4 characters" />
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={allowDownload} onChange={(e) => setAllowDownload(e.target.checked)} /> Allow downloading (otherwise view only)
          </label>
          <button
            type="button"
            className="btn-primary w-full"
            onClick={() =>
              guard(async () => {
                const s = await documents.share(doc.id, { expires_in_days: days || null, password: password || null, max_downloads: maxDownloads || null, allow_download: allowDownload });
                await navigator.clipboard?.writeText(s.url).catch(() => {});
                setPassword("");
              }, "Link created and copied.")
            }
          >
            <Link2 className="h-4 w-4" /> Create link
          </button>
        </section>

        <form
          className="mt-5 space-y-2 border-t border-slate-200 pt-4 text-sm dark:border-slate-800"
          onSubmit={(e) => {
            e.preventDefault();
            guard(() => documents.send(doc.id, { email, message }), `Sent to ${email}.`).then(() => setEmail(""));
          }}
        >
          <p className="font-medium">Send by email</p>
          <input className="input py-1" type="email" required placeholder="name@example.com" aria-label="Recipient email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <textarea className="input py-1" rows={2} placeholder="Message (optional)" value={message} onChange={(e) => setMessage(e.target.value)} />
          <button className="btn-secondary w-full">
            <Mail className="h-4 w-4" /> Send link
          </button>
        </form>

        {note && <p className="mt-3 text-sm text-emerald-700 dark:text-emerald-300">{note}</p>}
        {error && <p className="mt-3 text-sm text-rose-600">{error}</p>}

        {shares.length > 0 && (
          <div className="mt-5 border-t border-slate-200 pt-4 dark:border-slate-800">
            <p className="mb-2 text-sm font-medium">Active links</p>
            <ul className="space-y-2 text-sm">
              {shares.map((s) => (
                <li key={s.id} className="rounded-lg border border-slate-200 p-2 dark:border-slate-700">
                  <div className="flex items-center gap-2">
                    <code className="min-w-0 flex-1 truncate text-xs">{s.url}</code>
                    <button type="button" className="btn-ghost px-1.5 py-1" aria-label="Copy link" onClick={() => copy(s.url, "Link")}>
                      <Copy className="h-3.5 w-3.5" />
                    </button>
                    <button type="button" className="btn-ghost px-1.5 py-1 text-xs" onClick={() => copy(s.embed, "Embed code")}>
                      Embed
                    </button>
                    <button type="button" className="btn-ghost px-1.5 py-1 text-rose-600" aria-label="Turn off link" onClick={() => guard(() => documents.revoke(doc.id, s.id), "Link turned off.")}>
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    {s.views} views · {s.downloads}
                    {s.max_downloads ? `/${s.max_downloads}` : ""} downloads
                    {s.has_password && " · password"}
                    {!s.allow_download && " · view only"}
                    {s.sent_to && ` · sent to ${s.sent_to}`}
                    {s.expires_at ? ` · expires ${new Date(s.expires_at).toLocaleDateString()}` : " · never expires"}
                  </p>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
