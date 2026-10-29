"use client";

import { Trash2, UserPlus, Users } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { useSession } from "@/components/AppProviders";
import { api } from "@/lib/api";
import type { Team } from "@/lib/types";

export default function TeamsPage() {
  const { user, loading, refresh } = useSession();
  const [teams, setTeams] = useState<Team[]>([]);
  const [active, setActive] = useState<Team | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("member");
  const [error, setError] = useState<string | null>(null);

  const load = async (select?: string) => {
    const r = await api.teams();
    setTeams(r.teams);
    const id = select ?? active?.id ?? r.teams[0]?.id;
    setActive(id ? await api.team(id) : null);
  };
  useEffect(() => {
    if (user) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  const guard = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  if (loading) return null;
  if (!user)
    return (
      <div className="container-page py-16 text-center">
        <Link href="/login?next=/teams" className="btn-primary">Sign in to manage teams</Link>
      </div>
    );

  const canAdmin = active && (active.role === "owner" || active.role === "admin");

  return (
    <div className="container-page py-10">
      <h1 className="text-3xl font-bold">Teams</h1>
      <p className="mt-1 text-slate-500">Share a Business plan, workflows and API access with your colleagues.</p>
      <div className="mt-8 grid gap-6 md:grid-cols-[16rem_1fr]">
        <aside className="space-y-2">
          {teams.map((t) => (
            <button key={t.id} onClick={() => load(t.id)} className={`card w-full p-3 text-left ${active?.id === t.id ? "ring-2 ring-brand-600" : ""}`}>
              <p className="font-medium">{t.name}</p>
              <p className="text-xs capitalize text-slate-500">{t.plan} · {t.role}</p>
            </button>
          ))}
          <form className="card space-y-2 p-3" onSubmit={(e) => (e.preventDefault(), guard(async () => {
            const t = await api.createTeam(name);
            setName("");
            await load(t.id);
          }))}>
            <input className="input" placeholder="New team name" value={name} onChange={(e) => setName(e.target.value)} required />
            <button className="btn-secondary w-full"><Users className="h-4 w-4" /> Create team</button>
          </form>
        </aside>
        {active ? (
          <section className="card p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-xl font-semibold">{active.name}</h2>
                <p className="text-sm capitalize text-slate-500">{active.plan} plan · {active.seats_used}/{active.seats} seats used</p>
              </div>
              {active.plan !== "business" && active.role === "owner" && <Link href="/pricing" className="btn-primary">Upgrade to Business</Link>}
            </div>
            {error && <p role="alert" className="mt-4 text-sm text-rose-600">{error}</p>}
            <h3 className="mt-6 text-sm font-semibold uppercase tracking-wide text-slate-500">Members</h3>
            <ul className="mt-2 divide-y divide-slate-100 dark:divide-slate-800">
              {active.members?.map((m) => (
                <li key={m.user_id} className="flex items-center justify-between gap-3 py-3">
                  <div>
                    <p className="font-medium">{m.name || m.email}</p>
                    <p className="text-xs text-slate-500">{m.email}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {active.role === "owner" && m.user_id !== user.id ? (
                      <select className="input w-28" value={m.role} onChange={(e) => guard(async () => setActive(await api.setRole(active.id, m.user_id, e.target.value)))}>
                        <option value="owner">Owner</option>
                        <option value="admin">Admin</option>
                        <option value="member">Member</option>
                      </select>
                    ) : (
                      <span className="chip border-slate-200 capitalize">{m.role}</span>
                    )}
                    {(canAdmin || m.user_id === user.id) && (
                      <button className="btn-ghost p-2" aria-label={m.user_id === user.id ? "Leave team" : "Remove member"} onClick={() => guard(async () => {
                        await api.removeMember(active.id, m.user_id);
                        if (m.user_id === user.id) {
                          await refresh();
                          await load(undefined);
                        } else await load(active.id);
                      })}>
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
            {!!active.invitations?.length && (
              <>
                <h3 className="mt-6 text-sm font-semibold uppercase tracking-wide text-slate-500">Pending invitations</h3>
                <ul className="mt-2 space-y-2">
                  {active.invitations.map((i) => (
                    <li key={i.id} className="flex items-center justify-between text-sm">
                      {i.email} <span className="text-slate-500">({i.role})</span>
                      {canAdmin && <button className="btn-ghost px-2 py-1 text-xs" onClick={() => guard(async () => (await api.revokeInvite(active.id, i.id), await load(active.id)))}>Revoke</button>}
                    </li>
                  ))}
                </ul>
              </>
            )}
            {canAdmin && (
              <form className="mt-6 flex flex-wrap gap-2" onSubmit={(e) => (e.preventDefault(), guard(async () => {
                setActive(await api.invite(active.id, email, role));
                setEmail("");
              }))}>
                <input type="email" required className="input flex-1" placeholder="colleague@company.com" value={email} onChange={(e) => setEmail(e.target.value)} />
                <select className="input w-32" value={role} onChange={(e) => setRole(e.target.value)}>
                  <option value="member">Member</option>
                  <option value="admin">Admin</option>
                </select>
                <button className="btn-primary"><UserPlus className="h-4 w-4" /> Invite</button>
              </form>
            )}
          </section>
        ) : (
          <p className="text-slate-500">Create a team to get started.</p>
        )}
      </div>
    </div>
  );
}
