"use client";

import { Download, FileText, Lock, XCircle } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { documents, type Shared } from "@/lib/documents";
import { formatBytes } from "@/lib/format";

import { PdfViewer } from "./PdfViewer";

/** What someone sees when they open a share link. With ?embed=1 it shows only the viewer, for iframes. */
export function SharedFile({ token }: { token: string }) {
  const embed = useSearchParams().get("embed") === "1";
  const [meta, setMeta] = useState<Shared | null>(null);
  const [grant, setGrant] = useState<string | null>(null);
  const [data, setData] = useState<ArrayBuffer | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    documents.shared(token).then(
      (m) => (setMeta(m), setGrant(m.grant)),
      (e) => setError(e.message),
    );
  }, [token]);

  useEffect(() => {
    if (!grant || !meta || meta.content_type !== "application/pdf") return;
    fetch(documents.sharedFileUrl(token, grant))
      .then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(new Error("The file couldn't be loaded."))))
      .then(setData, (e) => setError(e.message));
  }, [grant, meta, token]);

  const download = () => grant && (window.location.href = documents.sharedFileUrl(token, grant, true));

  if (error && !meta)
    return (
      <div className="container-page flex flex-col items-center py-20 text-center">
        <XCircle className="mb-3 h-10 w-10 text-slate-400" />
        <h1 className="text-xl font-semibold">{error}</h1>
      </div>
    );
  if (!meta) return <div className="container-page py-16 text-center text-slate-500">Loading…</div>;

  if (!grant)
    return (
      <form
        className="container-page flex max-w-sm flex-col items-center gap-3 py-20 text-center"
        onSubmit={async (e) => {
          e.preventDefault();
          setError(null);
          documents.unlock(token, password).then((r) => setGrant(r.grant), (err) => setError(err.message));
        }}
      >
        <Lock className="h-10 w-10 text-brand-600" />
        <h1 className="text-xl font-semibold">{meta.shared_by} shared “{meta.name}”</h1>
        <p className="text-sm text-slate-500">Enter the password to open it.</p>
        <input type="password" className="input" aria-label="Password" value={password} onChange={(e) => setPassword(e.target.value)} autoFocus />
        {error && <p className="text-sm text-rose-600">{error}</p>}
        <button className="btn-primary w-full">Open</button>
      </form>
    );

  if (meta.content_type !== "application/pdf")
    return (
      <div className="container-page flex max-w-md flex-col items-center gap-3 py-20 text-center">
        <FileText className="h-10 w-10 text-brand-600" />
        <h1 className="text-xl font-semibold">{meta.name}</h1>
        <p className="text-sm text-slate-500">
          Shared by {meta.shared_by} · {formatBytes(meta.size)}
        </p>
        {meta.allow_download ? (
          <button type="button" className="btn-primary" onClick={download}>
            <Download className="h-4 w-4" /> Download
          </button>
        ) : (
          <p className="text-sm text-slate-500">The owner turned off downloads for this file.</p>
        )}
      </div>
    );

  if (embed)
    // Covers the site header and footer so an iframe shows only the document.
    return (
      <div className="fixed inset-0 z-[100] bg-white dark:bg-slate-950">
        {data && <PdfViewer data={data} name={meta.name} compact className="h-full rounded-none border-0" onDownload={meta.allow_download ? download : undefined} />}
      </div>
    );

  return (
    <div className="container-page py-4">
      <p className="mb-2 text-sm text-slate-500">
        Shared by <b>{meta.shared_by}</b>
        {meta.expires_at && ` · link expires ${new Date(meta.expires_at).toLocaleDateString()}`}
      </p>
      {error && <p className="text-sm text-rose-600">{error}</p>}
      {data && <PdfViewer data={data} name={meta.name} className="h-[calc(100vh-9rem)]" onDownload={meta.allow_download ? download : undefined} />}
    </div>
  );
}
