"use client";

import { Send } from "lucide-react";
import { useState } from "react";

import { serverEngine } from "@/lib/engines";

type Turn = { role: "user" | "assistant"; content: string };

/** Q&A over one PDF. Each question is a server task, so plan limits and auto-deletion still apply. */
export function ChatPanel({ file }: { file: File }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask(e: React.FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q || busy) return;
    setBusy(true);
    setError(null);
    setQuestion("");
    const history = turns.slice(-10);
    setTurns([...turns, { role: "user", content: q }]);
    try {
      const result = await serverEngine.run("ai_chat", [file], { question: q, history }, () => {});
      const answer = await result.blob.text();
      setTurns((t) => [...t, { role: "assistant", content: answer }]);
      if (result.job) fetch(`/api/jobs/${result.job.id}`, { method: "DELETE" }).catch(() => {});
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card flex h-[32rem] flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {!turns.length && <p className="text-center text-sm text-slate-500">Ask anything about “{file.name}”.</p>}
        {turns.map((t, i) => (
          <div key={i} className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm ${t.role === "user" ? "ml-auto bg-brand-600 text-white" : "bg-slate-100 dark:bg-slate-800"}`}>
            {t.content}
          </div>
        ))}
        {busy && <div className="w-24 animate-pulse rounded-2xl bg-slate-100 px-4 py-2 text-sm dark:bg-slate-800">Thinking…</div>}
        {error && <p className="text-sm text-rose-600">{error}</p>}
      </div>
      <form onSubmit={ask} className="flex gap-2 border-t border-slate-200 p-3 dark:border-slate-800">
        <input className="input" placeholder="What is the termination clause?" value={question} onChange={(e) => setQuestion(e.target.value)} aria-label="Your question" />
        <button className="btn-primary" disabled={busy || !question.trim()} aria-label="Send">
          <Send className="h-4 w-4" />
        </button>
      </form>
    </div>
  );
}
