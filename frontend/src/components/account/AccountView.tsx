"use client";

import { Copy, Download, KeyRound, LogOut, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useSession } from "@/components/AppProviders";
import { api } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { getTool } from "@/lib/tools";
import type { Job } from "@/lib/types";

const TABS = ["overview", "history", "billing", "api", "privacy"] as const;
type Tab = (typeof TABS)[number];
const TAB_LABELS: Record<Tab, string> = { overview: "Overview", history: "History", billing: "Billing", api: "API keys", privacy: "Privacy & security" };

export function AccountView() {
  const { user, plan, loading } = useSession();
  const router = useRouter();
  const params = useSearchParams();
  const [tab, setTab] = useState<Tab>((params.get("tab") as Tab) || "overview");

  useEffect(() => {
    if (!loading && !user) router.replace("/login?next=/account");
  }, [loading, user, router]);

  if (!user || !plan) return <div className="container-page py-16 text-center text-slate-500">Loading…</div>;

  return (
    <div className="container-page py-10">
      <h1 className="text-3xl font-bold">Your account</h1>
      {params.get("status") === "success" && (
        <p className="mt-4 rounded-xl bg-emerald-50 p-4 text-sm text-emerald-800 dark:bg-emerald-500/10 dark:text-emerald-200">
          Payment received. Your plan updates as soon as the payment provider confirms it, usually within a minute.
        </p>
      )}
      <div className="mt-6 flex gap-1 overflow-x-auto border-b border-slate-200 dark:border-slate-800">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`whitespace-nowrap border-b-2 px-4 py-2 text-sm font-medium ${tab === t ? "border-brand-600 text-brand-700 dark:text-brand-300" : "border-transparent text-slate-500"}`}>
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>
      <div className="mt-6">
        {tab === "overview" && <Overview />}
        {tab === "history" && <History />}
        {tab === "billing" && <Billing />}
        {tab === "api" && <ApiKeys />}
        {tab === "privacy" && <Privacy />}
      </div>
    </div>
  );
}

function Overview() {
  const { user, plan, refresh } = useSession();
  const [name, setName] = useState(user?.name ?? "");
  const [saved, setSaved] = useState(false);
  return (
    <div className="grid gap-6 md:grid-cols-2">
      <div className="card p-6">
        <h2 className="font-semibold">Plan</h2>
        <p className="mt-2 text-3xl font-bold">{plan!.name}</p>
        <ul className="mt-4 space-y-1 text-sm text-slate-600 dark:text-slate-400">
          <li>Files up to {plan!.max_file_mb} MB, {plan!.max_files_per_task} per task</li>
          <li>{plan!.tasks_per_day ? `${plan!.tasks_per_day} server tasks a day` : "Unlimited server tasks"}</li>
          <li>{plan!.premium_tools ? "All Pro tools included" : "Pro tools locked"}</li>
          <li>{plan!.team_workspace ? "Team workspace included" : "No team workspace"}</li>
        </ul>
        <div className="mt-6 flex gap-2">
          {!plan!.premium_tools && <Link href="/pricing" className="btn-primary">Upgrade</Link>}
          <Link href="/teams" className="btn-secondary">Teams</Link>
        </div>
      </div>
      <div className="card p-6">
        <h2 className="font-semibold">Profile</h2>
        <p className="mt-2 text-sm text-slate-500">{user!.email}</p>
        <label className="label mt-4" htmlFor="name">Name</label>
        <div className="flex gap-2">
          <input id="name" className="input" value={name} onChange={(e) => (setName(e.target.value), setSaved(false))} />
          <button className="btn-secondary" onClick={async () => (await api.updateProfile(name), await refresh(), setSaved(true))}>
            {saved ? "Saved" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

function History() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  useEffect(() => {
    api.jobs().then((r) => setJobs(r.jobs)).catch(() => setJobs([]));
  }, []);
  if (!jobs) return <p className="text-slate-500">Loading…</p>;
  if (!jobs.length) return <p className="text-slate-500">No server tasks yet. On-device tasks are never recorded.</p>;
  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs uppercase text-slate-500">
          <tr>
            <th className="p-3">Tool</th>
            <th className="p-3">Files</th>
            <th className="p-3">Status</th>
            <th className="p-3">When</th>
            <th className="p-3" />
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.id} className="border-t border-slate-100 dark:border-slate-800">
              <td className="p-3 font-medium">{j.steps.map((s) => getTool(s.tool)?.name ?? s.tool).join(" → ")}</td>
              <td className="max-w-xs truncate p-3 text-slate-500" title={j.inputs.join(", ")}>{j.inputs.join(", ") || "—"}</td>
              <td className="p-3">
                <span className={`chip ${j.status === "succeeded" ? "border-emerald-200 text-emerald-700" : j.status === "failed" ? "border-rose-200 text-rose-700" : "border-slate-200"}`}>{j.status}</span>
              </td>
              <td className="p-3 text-slate-500">{new Date(j.created_at).toLocaleString()}</td>
              <td className="p-3 text-right">
                {j.download_url && new Date(j.expires_at) > new Date() ? (
                  <a className="btn-ghost px-2 py-1" href={j.download_url}>
                    <Download className="h-4 w-4" /> {formatBytes(j.output_bytes)}
                  </a>
                ) : (
                  <span className="text-xs text-slate-400">Deleted</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Billing() {
  const [subs, setSubs] = useState<Awaited<ReturnType<typeof api.subscriptions>>["subscriptions"] | null>(null);
  const load = () => api.subscriptions().then((r) => setSubs(r.subscriptions)).catch(() => setSubs([]));
  useEffect(() => {
    load();
  }, []);
  if (!subs) return <p className="text-slate-500">Loading…</p>;
  if (!subs.length)
    return (
      <p className="text-slate-500">
        No subscriptions. <Link href="/pricing" className="text-brand-600">See plans</Link>
      </p>
    );
  return (
    <div className="space-y-3">
      {subs.map((s) => (
        <div key={s.id} className="card flex flex-wrap items-center justify-between gap-3 p-5">
          <div>
            <p className="font-semibold capitalize">
              {s.plan} {s.owner_type === "team" && `(team, ${s.seats} seats)`}
            </p>
            <p className="text-sm text-slate-500">
              {s.provider} · {s.status}
              {s.current_period_end && ` · renews ${new Date(s.current_period_end).toLocaleDateString()}`}
            </p>
          </div>
          {s.status === "active" && (
            <button
              className="btn-secondary"
              onClick={async () => {
                if (confirm("Cancel this subscription? You keep access until the end of the period.")) {
                  await api.cancelSubscription(s.id);
                  load();
                }
              }}
            >
              Cancel
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

function ApiKeys() {
  const [data, setData] = useState<Awaited<ReturnType<typeof api.apiKeys>> | null>(null);
  const [name, setName] = useState("");
  const [created, setCreated] = useState<string | null>(null);
  const load = () => api.apiKeys().then(setData);
  useEffect(() => {
    load();
  }, []);
  return (
    <div className="space-y-6">
      {data && (
        <div className="card p-6">
          <p className="text-sm text-slate-500">This month</p>
          <p className="mt-1 text-2xl font-bold">
            {data.usage.used} / {data.usage.included} credits
          </p>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
            <div className="h-full bg-brand-600" style={{ width: `${Math.min(100, (data.usage.used / Math.max(1, data.usage.included)) * 100)}%` }} />
          </div>
          <p className="help">One credit per task. <Link href="/developers" className="text-brand-600">Read the API docs</Link></p>
        </div>
      )}
      <div className="card p-6">
        <h2 className="font-semibold">Create a key</h2>
        <form
          className="mt-3 flex gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            const r = await api.createApiKey(name || "API key");
            setCreated(r.key);
            setName("");
            load();
          }}
        >
          <input className="input" placeholder="e.g. Production server" value={name} onChange={(e) => setName(e.target.value)} />
          <button className="btn-primary">
            <KeyRound className="h-4 w-4" /> Create
          </button>
        </form>
        {created && (
          <div className="mt-4 rounded-xl bg-amber-50 p-4 text-sm dark:bg-amber-500/10">
            <p className="font-medium">Copy your key now. You won't see it again.</p>
            <div className="mt-2 flex gap-2">
              <code className="input overflow-x-auto font-mono text-xs">{created}</code>
              <button className="btn-secondary" onClick={() => navigator.clipboard.writeText(created)} aria-label="Copy">
                <Copy className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}
      </div>
      {data?.keys.map((k) => (
        <div key={k.id} className="card flex items-center justify-between p-4">
          <div>
            <p className="font-medium">{k.name}</p>
            <p className="font-mono text-xs text-slate-500">
              {k.prefix}… · created {new Date(k.created_at).toLocaleDateString()}
              {k.last_used_at && ` · last used ${new Date(k.last_used_at).toLocaleDateString()}`}
            </p>
          </div>
          <button className="btn-ghost text-rose-600" onClick={async () => (await api.revokeApiKey(k.id), load())}>
            <Trash2 className="h-4 w-4" /> Revoke
          </button>
        </div>
      ))}
    </div>
  );
}

function Privacy() {
  const { user, refresh } = useSession();
  const router = useRouter();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <div className="card p-6">
        <h2 className="font-semibold">{user?.has_password ? "Change password" : "Set a password"}</h2>
        <form
          className="mt-3 space-y-3"
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              await api.changePassword(user?.has_password ? current : null, next);
              await refresh();
              router.push("/login");
            } catch (err) {
              setMsg((err as Error).message);
            }
          }}
        >
          {user?.has_password && <input type="password" className="input" placeholder="Current password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" />}
          <input type="password" className="input" placeholder="New password (8+ characters)" minLength={8} value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" />
          {msg && <p className="text-sm text-rose-600">{msg}</p>}
          <button className="btn-secondary">Save password</button>
        </form>
        <button className="btn-ghost mt-4" onClick={async () => (await api.logoutAll(), await refresh(), router.push("/login"))}>
          <LogOut className="h-4 w-4" /> Sign out on all devices
        </button>
      </div>
      <div className="card p-6">
        <h2 className="font-semibold">Your data</h2>
        <p className="mt-2 text-sm text-slate-500">
          Download everything we store about you, or delete your account and all associated data permanently.
        </p>
        <a href="/api/me/export" className="btn-secondary mt-4">
          <Download className="h-4 w-4" /> Export my data
        </a>
        <div className="mt-6 border-t border-slate-200 pt-6 dark:border-slate-800">
          <button
            className="btn-danger"
            onClick={async () => {
              if (prompt('Type "delete" to permanently delete your account.') === "delete") {
                await api.deleteAccount();
                await refresh();
                router.push("/");
              }
            }}
          >
            <Trash2 className="h-4 w-4" /> Delete account
          </button>
        </div>
      </div>
    </div>
  );
}
