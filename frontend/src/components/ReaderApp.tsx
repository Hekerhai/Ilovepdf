"use client";

import { ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { Dropzone } from "./Dropzone";
import { PdfViewer } from "./PdfViewer";
import { fromUrl } from "@/lib/importers";

type Opened = { name: string; data: ArrayBuffer; file: File; fetched?: boolean };

type LaunchParams = { files: { getFile: () => Promise<File> }[] };
declare global {
  interface Window {
    launchQueue?: { setConsumer: (fn: (p: LaunchParams) => void) => void };
  }
}

/** The PDF Reader: everything happens on this device, nothing is uploaded. */
export function ReaderApp() {
  const [opened, setOpened] = useState<Opened | null>(null);

  const [error, setError] = useState<string | null>(null);
  const open = async (file: File, fetched = false) => setOpened({ name: file.name, data: await file.arrayBuffer(), file, fetched });

  useEffect(() => {
    // Opened from the installed app ("Open with" on desktop) or shared to it on a phone.
    window.launchQueue?.setConsumer(async (params) => {
      const handle = params.files?.[0];
      if (handle) open(await handle.getFile());
    });
    const link = new URLSearchParams(window.location.search).get("import");
    if (link) fromUrl(link).then((f) => open(f, true), (e) => setError(e.message));
    if (new URLSearchParams(window.location.search).has("shared")) {
      caches
        .open("folio-share-target")
        .then((cache) => cache.match("/shared-file"))
        .then(async (res) => {
          if (!res) return;
          const name = decodeURIComponent(res.headers.get("x-file-name") ?? "shared.pdf");
          open(new File([await res.blob()], name, { type: "application/pdf" }));
        })
        .catch(() => {});
    }
  }, []);

  if (opened) {
    return (
      <div className="container-page py-4">
        <div className="mb-2 flex items-center justify-between text-sm">
          <span className="flex items-center gap-1.5 text-slate-500">
            <ShieldCheck className="h-4 w-4 text-emerald-600" /> {opened.fetched ? "Fetched from the link and shown on this device. Nothing was kept." : "Opened on this device. Nothing was uploaded."}
          </span>
          <button type="button" className="btn-ghost px-3 py-1.5" onClick={() => setOpened(null)}>
            Open another
          </button>
        </div>
        <PdfViewer
          data={opened.data}
          name={opened.name}
          className="h-[calc(100vh-9rem)]"
          onDownload={() => {
            const url = URL.createObjectURL(opened.file);
            const a = Object.assign(document.createElement("a"), { href: url, download: opened.name });
            a.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
          }}
        />
      </div>
    );
  }

  return (
    <div className="container-page max-w-3xl py-12">
      <h1 className="text-3xl font-extrabold tracking-tight">PDF Reader</h1>
      <p className="mb-6 mt-2 text-slate-600 dark:text-slate-400">
        Read, search and navigate PDFs right in your browser. Press Ctrl+F to search. The file stays on your device.
      </p>
      {error && <p className="mb-4 rounded-lg bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">{error}</p>}
      <Dropzone accept={[".pdf"]} multiple={false} onFiles={(f) => f[0] && open(f[0])} />
    </div>
  );
}
