"use client";

import { Cloud, FolderOpen, HardDrive, Link2, Loader2, X } from "lucide-react";
import { useState } from "react";

import { useSession } from "@/components/AppProviders";
import { type Doc, documents } from "@/lib/documents";
import { fromUrl, pickDropbox, pickGoogleDrive } from "@/lib/importers";

/** "Or add from…" a link, Dropbox, Google Drive or My documents. Hands back files like the file picker does. */
export function ImportSources({ accept, multiple, onFiles }: { accept: string[]; multiple: boolean; onFiles: (files: File[]) => void }) {
  const { config, user } = useSession();
  const [mode, setMode] = useState<"link" | "documents" | null>(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const dropbox = config?.pickers?.dropbox_app_key;
  const google = config?.pickers?.google;

  const fits = (name: string) => accept.some((ext) => name.toLowerCase().endsWith(ext));
  async function run(get: () => Promise<File[]>) {
    setError(null);
    setBusy(true);
    try {
      const files = await get();
      const ok = files.filter((f) => fits(f.name));
      if (files.length && !ok.length) throw new Error(`This tool takes ${accept.join(", ")} files.`);
      if (ok.length) {
        onFiles(multiple ? ok : ok.slice(0, 1));
        setMode(null);
        setUrl("");
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function openDocuments() {
    setMode(mode === "documents" ? null : "documents");
    if (!docs) documents.list().then((r) => setDocs(r.documents), (e) => setError(e.message));
  }

  const chip = "inline-flex items-center gap-1.5 rounded-full border border-slate-300 px-3 py-1 text-sm hover:border-brand-400 hover:text-brand-700 dark:border-slate-700 dark:hover:text-brand-300";
  return (
    <div className="mt-4 w-full max-w-xl" data-testid="import-sources">
      <div className="flex flex-wrap items-center justify-center gap-2">
        <span className="text-sm text-slate-500">or add from</span>
        <button type="button" className={chip} onClick={() => setMode(mode === "link" ? null : "link")} aria-expanded={mode === "link"}>
          <Link2 className="h-3.5 w-3.5" /> A link
        </button>
        {dropbox && (
          <button type="button" className={chip} disabled={busy} onClick={() => run(() => pickDropbox(dropbox, { multiple, extensions: accept }))}>
            <Cloud className="h-3.5 w-3.5" /> Dropbox
          </button>
        )}
        {google && (
          <button type="button" className={chip} disabled={busy} onClick={() => run(() => pickGoogleDrive(google, { multiple }))}>
            <HardDrive className="h-3.5 w-3.5" /> Google Drive
          </button>
        )}
        {user && (
          <button type="button" className={chip} onClick={openDocuments} aria-expanded={mode === "documents"}>
            <FolderOpen className="h-3.5 w-3.5" /> My documents
          </button>
        )}
      </div>
      {mode === "link" && (
        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (url.trim()) run(async () => [await fromUrl(url.trim())]);
          }}
        >
          <input className="input flex-1" type="url" inputMode="url" aria-label="File link" placeholder="https://… (Google Drive and Dropbox share links work too)" value={url} onChange={(e) => setUrl(e.target.value)} autoFocus />
          <button type="submit" className="btn-secondary" disabled={busy || !url.trim()}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Add"}
          </button>
        </form>
      )}
      {mode === "documents" && (
        <div className="mt-3 max-h-64 overflow-y-auto rounded-xl border border-slate-200 text-left dark:border-slate-800">
          <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2 text-sm font-medium dark:border-slate-800">
            My documents
            <button type="button" className="btn-ghost px-1 py-0.5" aria-label="Close" onClick={() => setMode(null)}>
              <X className="h-4 w-4" />
            </button>
          </div>
          {!docs && <p className="p-3 text-sm text-slate-500">Loading…</p>}
          {docs && !docs.filter((d) => fits(d.name)).length && <p className="p-3 text-sm text-slate-500">No saved {accept.join(", ")} files.</p>}
          <ul>
            {docs
              ?.filter((d) => fits(d.name))
              .map((d) => (
                <li key={d.id}>
                  <button
                    type="button"
                    className="w-full truncate px-3 py-2 text-left text-sm hover:bg-slate-50 dark:hover:bg-slate-900"
                    disabled={busy}
                    onClick={() =>
                      run(async () => {
                        const res = await fetch(documents.fileUrl(d.id), { credentials: "same-origin" });
                        if (!res.ok) throw new Error("That document couldn't be opened.");
                        return [new File([await res.blob()], d.name, { type: d.content_type })];
                      })
                    }
                  >
                    {d.name}
                  </button>
                </li>
              ))}
          </ul>
        </div>
      )}
      {busy && mode !== "link" && <p className="mt-2 text-center text-sm text-slate-500">Fetching…</p>}
      {error && <p className="mt-2 text-center text-sm text-rose-600">{error}</p>}
    </div>
  );
}
