"use client";

import { Check } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api, type BillingCatalog } from "@/lib/api";
import { money } from "@/lib/format";
import type { Team } from "@/lib/types";

import { useSession } from "./AppProviders";

export function PricingTable() {
  const { user, plan } = useSession();
  const router = useRouter();
  const [catalog, setCatalog] = useState<BillingCatalog | null>(null);
  const [interval, setBillingInterval] = useState<"month" | "year">("year");
  const [currency, setCurrency] = useState<"usd" | "inr">("usd");
  const [teams, setTeams] = useState<Team[]>([]);
  const [seats, setSeats] = useState(3);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.plans().then(setCatalog).catch(() => setError("Couldn't load plans."));
    if (Intl.DateTimeFormat().resolvedOptions().timeZone === "Asia/Calcutta" || navigator.language.endsWith("-IN")) setCurrency("inr");
  }, []);
  useEffect(() => {
    if (user) api.teams().then((r) => setTeams(r.teams.filter((t) => t.role === "owner"))).catch(() => {});
  }, [user]);

  async function buy(planId: string) {
    if (!user) {
      router.push(`/register?next=/pricing`);
      return;
    }
    setBusy(planId);
    setError(null);
    try {
      let teamId: string | undefined;
      if (planId === "business") {
        teamId = teams[0]?.id ?? (await api.createTeam(`${user.name || user.email.split("@")[0]}'s team`)).id;
      }
      const session = await api.checkout({
        plan: planId,
        interval,
        provider: currency === "inr" ? "razorpay" : "stripe",
        seats: planId === "business" ? seats : 1,
        team_id: teamId,
      });
      if (session.url) window.location.href = session.url;
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function buyPass() {
    if (!user) {
      router.push(`/register?next=/pricing`);
      return;
    }
    setBusy("pass");
    setError(null);
    try {
      const session = await api.buyPass(currency === "inr" ? "razorpay" : "stripe");
      if (session.url) window.location.href = session.url;
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  if (!catalog) return <div className="mx-auto mt-12 h-96 max-w-5xl animate-pulse rounded-2xl bg-slate-200 dark:bg-slate-800" />;

  return (
    <div className="mt-10">
      <div className="flex flex-wrap items-center justify-center gap-4">
        <Toggle value={interval} onChange={setBillingInterval} options={[["month", "Monthly"], ["year", "Yearly (save 33%)"]]} />
        <Toggle value={currency} onChange={setCurrency} options={[["usd", "USD"], ["inr", "INR"]]} />
      </div>
      {error && <p role="alert" className="mt-4 text-center text-sm text-rose-600">{error}</p>}
      <div className="mx-auto mt-8 grid max-w-5xl gap-6 md:grid-cols-3">
        {catalog.plans.map((p) => {
          const price = p.prices[interval];
          const current = plan?.id === p.id;
          const featured = p.id === "pro";
          const perMonth = price ? (interval === "year" ? price[currency] / 12 : price[currency]) : 0;
          return (
            <div key={p.id} className={`card relative flex flex-col p-6 ${featured ? "ring-2 ring-brand-600" : ""}`}>
              {featured && <span className="chip absolute -top-3 left-6 border-brand-600 bg-brand-600 text-white">Most popular</span>}
              <h2 className="text-lg font-semibold">{p.name}</h2>
              <p className="mt-4">
                <span className="text-4xl font-extrabold">{price ? money(Math.round(perMonth), currency) : money(0, currency)}</span>
                <span className="text-sm text-slate-500"> /{p.per_seat ? "seat/" : ""}month</span>
              </p>
              <p className="h-5 text-xs text-slate-500">{price && interval === "year" ? `${money(price[currency], currency)} billed yearly` : ""}</p>
              <ul className="mt-6 flex-1 space-y-2 text-sm">
                {(p.highlights.length ? p.highlights : ["Every on-device tool", `${p.tasks_per_day ?? "Unlimited"} server tasks a day`, `Files up to ${p.max_file_mb} MB`]).map((h) => (
                  <li key={h} className="flex gap-2">
                    <Check className="h-4 w-4 shrink-0 text-emerald-600" /> {h}
                  </li>
                ))}
              </ul>
              {p.id === "business" && price && (
                <label className="mt-4 flex items-center justify-between text-sm">
                  Seats
                  <input type="number" min={p.min_seats} value={seats} onChange={(e) => setSeats(Math.max(p.min_seats, Number(e.target.value)))} className="input w-20" />
                </label>
              )}
              <div className="mt-6">
                {current ? (
                  <span className="btn-secondary w-full cursor-default">Your plan</span>
                ) : price ? (
                  <button className={`${featured ? "btn-primary" : "btn-secondary"} w-full`} disabled={busy !== null} onClick={() => buy(p.id)}>
                    {busy === p.id ? "Opening checkout…" : `Get ${p.name}`}
                  </button>
                ) : (
                  <Link href={user ? "/#tools" : "/register"} className="btn-secondary w-full">
                    {user ? "Use free tools" : "Sign up free"}
                  </Link>
                )}
              </div>
            </div>
          );
        })}
      </div>
      {catalog.pass && (
        <div className="card mx-auto mt-6 flex max-w-5xl flex-wrap items-center justify-between gap-4 p-5">
          <div>
            <h2 className="font-semibold">Just need it for a week?</h2>
            <p className="text-sm text-slate-600 dark:text-slate-400">
              Get everything in Pro for {catalog.pass.days} days for {money(catalog.pass[currency], currency)}. One payment, no subscription, nothing to cancel.
            </p>
          </div>
          <button type="button" className="btn-secondary" disabled={busy !== null} onClick={buyPass}>
            {busy === "pass" ? "Opening checkout…" : `Get a ${catalog.pass.days}-day pass`}
          </button>
        </div>
      )}
    </div>
  );
}

function Toggle<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: [T, string][] }) {
  return (
    <div className="inline-flex rounded-xl border border-slate-200 bg-white p-1 dark:border-slate-700 dark:bg-slate-900">
      {options.map(([v, label]) => (
        <button key={v} onClick={() => onChange(v)} className={`rounded-lg px-4 py-1.5 text-sm font-medium ${value === v ? "bg-brand-600 text-white" : "text-slate-600 dark:text-slate-300"}`}>
          {label}
        </button>
      ))}
    </div>
  );
}
