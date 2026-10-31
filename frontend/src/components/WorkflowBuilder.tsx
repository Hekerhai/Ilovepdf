"use client";

import { ArrowDown, Crown, LoaderCircle, Play, Plus, Save, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import { serverEngine } from "@/lib/engines";
import { downloadBlob } from "@/lib/format";
import { catalog, getTool } from "@/lib/tools";
import type { Step, Team, Workflow } from "@/lib/types";

import { useSession } from "./AppProviders";
import { Dropzone } from "./Dropzone";
import { defaultOptions, OptionsForm } from "./OptionsForm";
import { ToolIcon } from "./ToolCard";

/** Tools that need a visual editor can't be configured blind inside a workflow. */
const INTERACTIVE = new Set(["sign", "organize", "create_bookmarks", "ai_chat", "html_to_pdf", "edit_pdf", "annotate_pdf", "fill_forms", "create_forms"]);

const TEMPLATES: { name: string; steps: Step[] }[] = [
  { name: "Scan cleanup", steps: [{ tool: "ocr", options: {} }, { tool: "compress", options: { level: "recommended" } }] },
  { name: "Confidential release", steps: [{ tool: "watermark", options: { text: "CONFIDENTIAL" } }, { tool: "protect", options: { password: "" } }] },
  { name: "Print-ready", steps: [{ tool: "page_numbers", options: {} }, { tool: "grayscale", options: {} }, { tool: "compress", options: { level: "low" } }] },
];

export function WorkflowBuilder() {
  const { user, plan } = useSession();
  const [steps, setSteps] = useState<Step[]>([]);
  const [name, setName] = useState("My workflow");
  const [teamId, setTeamId] = useState<string>("");
  const [editing, setEditing] = useState<string | undefined>();
  const [saved, setSaved] = useState<Workflow[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const allowed = Boolean(plan?.workflows);

  const load = () => api.workflows().then((r) => setSaved(r.workflows)).catch(() => {});
  useEffect(() => {
    if (user && allowed) {
      load();
      api.teams().then((r) => setTeams(r.teams)).catch(() => {});
    }
  }, [user, allowed]);

  const candidates = useMemo(() => {
    const last = steps.length ? getTool(steps[steps.length - 1].tool) : null;
    if (last && !last.produces_pdf) return [];
    return catalog.tools.filter((t) => !INTERACTIVE.has(t.id) && (steps.length === 0 || t.accepts.includes(".pdf")));
  }, [steps]);

  const first = steps.length ? getTool(steps[0].tool) : null;

  async function run() {
    setRunning(true);
    setError(null);
    try {
      const result = await serverEngine.runSteps(steps, files, (m) => setStatus(m));
      downloadBlob(result.blob, result.name);
      setStatus(`Done: ${result.name}`);
    } catch (e) {
      setError((e as Error).message);
      setStatus(null);
    } finally {
      setRunning(false);
    }
  }

  async function save() {
    setError(null);
    try {
      const wf = await api.saveWorkflow(name, steps, teamId || null, editing);
      setEditing(wf.id);
      await load();
      setStatus("Workflow saved.");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="container-page py-10">
      <div className="max-w-2xl">
        <h1 className="text-3xl font-bold">Workflows</h1>
        <p className="mt-2 text-slate-600 dark:text-slate-400">
          Chain tools into one task and run it on many files. For example: OCR, then compress, then watermark, then protect.
        </p>
      </div>
      {!allowed && (
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-5 dark:border-amber-900 dark:bg-amber-500/10">
          <p className="text-sm">Workflows are part of Pro. You can design one here; running and saving needs Pro.</p>
          <Link href={user ? "/pricing" : "/register?next=/pricing"} className="btn-primary">
            <Crown className="h-4 w-4" /> Upgrade
          </Link>
        </div>
      )}
      <div className="mt-8 grid gap-6 lg:grid-cols-[1fr_20rem]">
        <section className="space-y-3">
          {!steps.length && (
            <div className="card p-6">
              <p className="font-medium">Start from a template</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {TEMPLATES.map((t) => (
                  <button key={t.name} className="btn-secondary px-3 py-1.5" onClick={() => (setSteps(t.steps.map((s) => ({ tool: s.tool, options: { ...defaultOptions(getTool(s.tool)!), ...s.options } }))), setName(t.name))}>
                    {t.name}
                  </button>
                ))}
              </div>
            </div>
          )}
          {steps.map((step, i) => {
            const tool = getTool(step.tool)!;
            return (
              <div key={i}>
                {i > 0 && <ArrowDown className="mx-auto mb-3 h-5 w-5 text-slate-400" />}
                <div className="card p-5">
                  <div className="mb-4 flex items-center gap-3">
                    <ToolIcon tool={tool} />
                    <div className="flex-1">
                      <p className="text-xs text-slate-500">Step {i + 1}</p>
                      <p className="font-semibold">{tool.name}</p>
                    </div>
                    <button className="btn-ghost p-2" aria-label="Remove step" onClick={() => setSteps(steps.filter((_, k) => k < i))}>
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                  <OptionsForm tool={tool} values={step.options} onChange={(options) => setSteps(steps.map((s, k) => (k === i ? { ...s, options } : s)))} />
                </div>
              </div>
            );
          })}
          {candidates.length > 0 && (
            <div className="card p-5">
              <label className="label" htmlFor="add-step">
                <Plus className="mr-1 inline h-4 w-4" /> {steps.length ? "Then…" : "First step"}
              </label>
              <select
                id="add-step"
                className="input"
                value=""
                onChange={(e) => {
                  const tool = getTool(e.target.value);
                  if (tool) setSteps([...steps, { tool: tool.id, options: defaultOptions(tool) }]);
                }}
              >
                <option value="">Choose a tool…</option>
                {catalog.categories.map((c) => (
                  <optgroup key={c.id} label={c.name}>
                    {candidates.filter((t) => t.category === c.id).map((t) => (
                      <option key={t.id} value={t.id}>{t.name}{t.premium ? " (Pro)" : ""}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </div>
          )}
        </section>
        <aside className="space-y-4">
          <div className="card space-y-3 p-5">
            <h2 className="font-semibold">Run</h2>
            {first ? (
              <>
                <Dropzone compact accept={first.accepts} multiple onFiles={(f) => setFiles([...files, ...f])} />
                {files.length > 0 && (
                  <p className="text-sm text-slate-500">
                    {files.length} file{files.length > 1 ? "s" : ""} ready{" "}
                    <button className="text-brand-600" onClick={() => setFiles([])}>clear</button>
                  </p>
                )}
                <button className="btn-primary w-full" disabled={!allowed || running || files.length < first.min_files} onClick={run}>
                  {running ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} Run workflow
                </button>
              </>
            ) : (
              <p className="text-sm text-slate-500">Add a step to begin.</p>
            )}
            {status && <p className="text-sm text-slate-500">{status}</p>}
            {error && <p role="alert" className="text-sm text-rose-600">{error}</p>}
          </div>
          <div className="card space-y-3 p-5">
            <h2 className="font-semibold">Save</h2>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} aria-label="Workflow name" />
            {teams.length > 0 && (
              <select className="input" value={teamId} onChange={(e) => setTeamId(e.target.value)} aria-label="Share with">
                <option value="">Only me</option>
                {teams.map((t) => <option key={t.id} value={t.id}>Share with {t.name}</option>)}
              </select>
            )}
            <button className="btn-secondary w-full" disabled={!allowed || !steps.length} onClick={save}>
              <Save className="h-4 w-4" /> {editing ? "Update" : "Save"} workflow
            </button>
          </div>
          {saved.length > 0 && (
            <div className="card p-5">
              <h2 className="font-semibold">Saved</h2>
              <ul className="mt-3 space-y-2">
                {saved.map((w) => (
                  <li key={w.id} className="flex items-center justify-between gap-2 text-sm">
                    <button className="truncate text-left text-brand-600" onClick={() => (setSteps(w.steps), setName(w.name), setEditing(w.id), setTeamId(w.team_id ?? ""))}>
                      {w.name}
                    </button>
                    <button className="btn-ghost p-1" aria-label={`Delete ${w.name}`} onClick={async () => (await api.deleteWorkflow(w.id), load())}>
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
