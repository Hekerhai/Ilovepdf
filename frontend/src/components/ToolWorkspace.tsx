"use client";

import { ArrowRight, Check, Crown, Download, LoaderCircle, RotateCcw, Server, ShieldCheck, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ApiError } from "@/lib/api";
import { chooseEngine } from "@/lib/engines";
import { downloadBlob, formatBytes } from "@/lib/format";
import { handOff, takeHandOff } from "@/lib/handoff";
import { acceptsPdf, catalog } from "@/lib/tools";
import type { ToolInfo, ToolResult } from "@/lib/types";

import { useSession } from "./AppProviders";
import { ChatPanel } from "./ChatPanel";
import { Dropzone } from "./Dropzone";
import { FileList } from "./FileList";
import { defaultOptions, OptionsForm, type OptionValues } from "./OptionsForm";
import { ToolIcon } from "./ToolCard";
import { FormBuilder } from "./widgets/FormBuilder";
import { FormFiller } from "./widgets/FormFiller";
import { PageOrganizer } from "./widgets/PageOrganizer";
import { PdfEditor } from "./widgets/PdfEditor";
import { SignWidget } from "./widgets/SignWidget";
import { BookmarksEditor, CertificatePicker, ImagePicker } from "./widgets/SmallWidgets";

type Status = { phase: "idle" } | { phase: "running"; message: string; fraction: number } | { phase: "done"; result: ToolResult } | { phase: "error"; message: string; code?: string };

const ORDERED_TOOLS = new Set(["merge", "images_to_pdf", "alternate_mix", "compare", "organize", "bates"]);
const NEXT_STEPS = ["edit_pdf", "compress", "protect", "watermark", "page_numbers", "sign", "split", "organize", "ocr", "pdf_to_word"];

/** Tools whose main input comes from an on-page widget; the run button waits until there is something to apply. */
function hasWidgetInput(toolId: string, values: OptionValues): boolean {
  if (toolId === "edit_pdf") return ((values.objects as unknown[]) ?? []).length > 0;
  if (toolId === "create_forms") return ((values.fields as unknown[]) ?? []).length > 0;
  if (toolId === "fill_forms") return Object.keys((values.fields as object) ?? {}).length > 0;
  return true;
}

export function ToolWorkspace({ tool }: { tool: ToolInfo }) {
  const { plan, user, config, refresh } = useSession();
  const router = useRouter();
  const [files, setFiles] = useState<File[]>([]);
  const [values, setValues] = useState<OptionValues>(() => defaultOptions(tool));
  const [privateMode, setPrivateMode] = useState(true);
  const [status, setStatus] = useState<Status>({ phase: "idle" });

  useEffect(() => {
    const incoming = takeHandOff().filter((f) => tool.accepts.some((ext) => f.name.toLowerCase().endsWith(ext)));
    if (incoming.length) setFiles(incoming);
  }, [tool]);

  const multiple = tool.max_files === null || tool.max_files > 1;
  const needsFiles = tool.min_files > 0;
  const { engine, browserBlocker } = useMemo(() => chooseEngine(tool.id, values, privateMode), [tool.id, values, privateMode]);
  const locked = tool.premium && plan !== null && !plan.premium_tools;
  const aiMissing = tool.category === "intelligence" && config !== null && !config.ai_available;
  const ready = (files.length >= tool.min_files || (!needsFiles && Boolean(values.url))) && hasWidgetInput(tool.id, values) && status.phase !== "running";

  async function run() {
    setStatus({ phase: "running", message: "Starting…", fraction: 0.02 });
    try {
      const result = await engine.run(tool.id, files, values, (message, fraction) =>
        setStatus({ phase: "running", message, fraction: fraction ?? 0.5 }),
      );
      setStatus({ phase: "done", result });
      if (result.where === "server") refresh();
    } catch (err) {
      const e = err as Error;
      setStatus({ phase: "error", message: e.message, code: err instanceof ApiError ? err.code : undefined });
    }
  }

  function reset() {
    setFiles([]);
    setValues(defaultOptions(tool));
    setStatus({ phase: "idle" });
  }

  function continueWith(nextId: string) {
    if (status.phase !== "done") return;
    const { blob, name } = status.result;
    handOff([new File([blob], name, { type: blob.type })]);
    router.push(`/tools/${nextId}`);
  }

  return (
    <div className="container-page py-10">
      <div className="mx-auto max-w-3xl text-center">
        <div className="flex justify-center">
          <ToolIcon tool={tool} size="lg" />
        </div>
        <h1 className="mt-4 text-3xl font-extrabold tracking-tight md:text-4xl">{tool.name}</h1>
        <p className="mt-2 text-slate-600 dark:text-slate-400">{tool.description}</p>
        <div className="mt-3 flex justify-center gap-2">
          {tool.browser_capable && (
            <span className="chip border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-500/10">
              <ShieldCheck className="h-3.5 w-3.5" /> Can run on your device
            </span>
          )}
          {tool.premium && (
            <span className="chip border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-500/10">
              <Crown className="h-3.5 w-3.5" /> Pro
            </span>
          )}
        </div>
      </div>

      {locked && (
        <div className="mx-auto mt-8 max-w-3xl rounded-2xl border border-amber-200 bg-amber-50 p-5 text-center dark:border-amber-900 dark:bg-amber-500/10">
          <p className="font-medium">{tool.name} is part of Pro.</p>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">Unlock OCR, PDF to Office, redaction, AI and workflows.</p>
          <Link href={user ? "/pricing" : "/register?next=/pricing"} className="btn-primary mt-4">
            <Crown className="h-4 w-4" /> See plans
          </Link>
        </div>
      )}
      {aiMissing && (
        <p className="mx-auto mt-6 max-w-3xl rounded-xl bg-slate-100 p-4 text-center text-sm dark:bg-slate-800">
          AI tools are not switched on for this server yet. An administrator can enable them by adding an AI provider key.
        </p>
      )}

      {status.phase === "done" ? (
        <ResultPanel tool={tool} result={status.result} inputBytes={files.reduce((s, f) => s + f.size, 0)} onReset={reset} onContinue={continueWith} />
      ) : tool.id === "ai_chat" && files.length ? (
        <div className="mx-auto mt-8 max-w-3xl">
          <ChatPanel file={files[0]} />
        </div>
      ) : (
        <div className="mx-auto mt-8 max-w-5xl">
          {needsFiles && !files.length ? (
            <Dropzone accept={tool.accepts} multiple={multiple} onFiles={setFiles} allowCamera={tool.id === "images_to_pdf" || tool.id === "scan_to_pdf"} />
          ) : (
            <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
              <div className="space-y-4">
                {tool.id === "organize" ? (
                  <PageOrganizer files={files} values={values} onChange={setValues} />
                ) : tool.id === "sign" && files[0] ? (
                  <SignWidget file={files[0]} values={values} onChange={setValues} />
                ) : tool.id === "edit_pdf" && files[0] ? (
                  <PdfEditor file={files[0]} values={values} onChange={setValues} />
                ) : tool.id === "create_forms" && files[0] ? (
                  <FormBuilder file={files[0]} values={values} onChange={setValues} />
                ) : tool.id === "fill_forms" && files[0] ? (
                  <FormFiller file={files[0]} values={values} onChange={setValues} />
                ) : (
                  <FileList files={files} onChange={setFiles} ordered={ORDERED_TOOLS.has(tool.id)} />
                )}
                {multiple && (
                  <Dropzone compact accept={tool.accepts} multiple onFiles={(more) => setFiles([...files, ...more])} />
                )}
              </div>
              <aside className="card h-fit space-y-5 p-5 lg:sticky lg:top-24">
                <h2 className="font-semibold">Options</h2>
                {tool.id === "watermark" && <ImagePicker values={values} onChange={setValues} />}
                {tool.id === "create_bookmarks" && <BookmarksEditor values={values} onChange={setValues} />}
                {tool.id === "digital_sign" && <CertificatePicker values={values} onChange={setValues} />}
                <OptionsForm tool={tool} values={values} onChange={setValues} />
                {tool.browser_capable && (
                  <div className="rounded-xl bg-slate-50 p-3 text-sm dark:bg-slate-800/60">
                    <label className="flex cursor-pointer items-center justify-between gap-3">
                      <span className="flex items-center gap-2 font-medium">
                        <ShieldCheck className="h-4 w-4 text-emerald-600" /> Private mode
                      </span>
                      <input type="checkbox" checked={privateMode} onChange={(e) => setPrivateMode(e.target.checked)} className="h-4 w-4 accent-brand-600" />
                    </label>
                    <p className="help">
                      {engine.where === "browser"
                        ? "Your files stay on this device."
                        : privateMode && browserBlocker
                          ? browserBlocker
                          : `Files are processed on our servers and deleted after ${config?.file_ttl_hours ?? 2} hours.`}
                    </p>
                  </div>
                )}
                {status.phase === "error" && <ErrorBox message={status.message} code={status.code} signedIn={Boolean(user)} />}
                {status.phase === "running" ? (
                  <div>
                    <div className="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                      <div className="h-full rounded-full bg-brand-600 transition-all" style={{ width: `${Math.round(status.fraction * 100)}%` }} />
                    </div>
                    <p className="mt-2 flex items-center gap-2 text-sm text-slate-500">
                      <LoaderCircle className="h-4 w-4 animate-spin" /> {status.message}
                    </p>
                  </div>
                ) : (
                  <button className="btn-primary w-full py-3 text-base" disabled={!ready || locked} onClick={run}>
                    {tool.name} <ArrowRight className="h-4 w-4" />
                  </button>
                )}
                {!needsFiles && !files.length && <Dropzone compact accept={tool.accepts} multiple={false} onFiles={setFiles} />}
              </aside>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ErrorBox({ message, code, signedIn }: { message: string; code?: string; signedIn: boolean }) {
  const upsell = code === "premium_required" || code === "daily_limit" || code === "file_too_large" || code === "too_many_files";
  return (
    <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-500/10 dark:text-rose-200">
      {message}
      {upsell && (
        <Link href={signedIn ? "/pricing" : "/register"} className="mt-2 block font-semibold underline">
          {signedIn ? "See plans" : "Create a free account"}
        </Link>
      )}
    </div>
  );
}

function ResultPanel({
  tool,
  result,
  inputBytes,
  onReset,
  onContinue,
}: {
  tool: ToolInfo;
  result: ToolResult;
  inputBytes: number;
  onReset: () => void;
  onContinue: (toolId: string) => void;
}) {
  const [deleted, setDeleted] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const saved = tool.id === "compress" && inputBytes > 0 ? 1 - result.blob.size / inputBytes : null;
  const isPdf = result.name.toLowerCase().endsWith(".pdf");
  const isText = /\.(md|txt)$/i.test(result.name);

  useEffect(() => {
    downloadBlob(result.blob, result.name);
    if (isText) result.blob.text().then(setPreview);
  }, [result, isText]);

  const nextTools = catalog.tools.filter((t) => NEXT_STEPS.includes(t.id) && t.id !== tool.id && acceptsPdf(t));

  return (
    <div className="mx-auto mt-8 max-w-3xl">
      <div className="card p-8 text-center">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-500/10">
          <Check className="h-7 w-7" />
        </div>
        <h2 className="mt-4 text-2xl font-bold">Done! Your download has started.</h2>
        <p className="mt-1 text-sm text-slate-500">
          {result.name} · {formatBytes(result.blob.size)}
          {saved !== null && saved > 0.005 && <span className="ml-2 font-semibold text-emerald-600">{Math.round(saved * 100)}% smaller</span>}
        </p>
        <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-slate-500">
          {result.where === "browser" ? (
            <>
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" /> Processed on your device. Nothing was uploaded.
            </>
          ) : (
            <>
              <Server className="h-3.5 w-3.5" /> {deleted ? "Deleted from our servers." : "Kept privately on our servers until it auto-deletes."}
            </>
          )}
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <button className="btn-primary px-6" onClick={() => downloadBlob(result.blob, result.name)}>
            <Download className="h-4 w-4" /> Download again
          </button>
          {result.job && !deleted && (
            <button
              className="btn-secondary"
              onClick={async () => {
                await fetch(`/api/jobs/${result.job!.id}`, { method: "DELETE" });
                setDeleted(true);
              }}
            >
              <Trash2 className="h-4 w-4" /> Delete from server now
            </button>
          )}
          <button className="btn-ghost" onClick={onReset}>
            <RotateCcw className="h-4 w-4" /> Start over
          </button>
        </div>
      </div>
      {preview !== null && (
        <pre className="card mt-6 max-h-96 overflow-auto whitespace-pre-wrap p-5 text-sm">{preview}</pre>
      )}
      {isPdf && (
        <div className="mt-8">
          <h3 className="text-center text-sm font-semibold uppercase tracking-wide text-slate-500">Continue with</h3>
          <div className="mt-3 flex flex-wrap justify-center gap-2">
            {nextTools.map((t) => (
              <button key={t.id} className="btn-secondary px-3 py-1.5" onClick={() => onContinue(t.id)}>
                {t.name}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
