"use client";

import { Mail } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { api } from "@/lib/api";

import { useSession } from "./AppProviders";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const { refresh, config } = useSession();
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") || "/account";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(params.get("error") ? "Sign-in failed. Please try again." : null);
  const [linkSent, setLinkSent] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "register") await api.register(email, password, name || undefined);
      else await api.login(email, password);
      await refresh();
      router.push(next.startsWith("/") ? next : "/account");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function sendLink() {
    if (!email) {
      setError("Enter your email first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.magicLink(email);
      setLinkSent(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="container-page flex justify-center py-16">
      <div className="card w-full max-w-md p-8">
        <h1 className="text-2xl font-bold">{mode === "login" ? "Welcome back" : "Create your free account"}</h1>
        <p className="mt-1 text-sm text-slate-500">
          {mode === "login" ? "Sign in to see your history, workflows and plan." : "More free tasks a day, history and team access."}
        </p>
        {config?.google_sign_in && (
          <a href="/api/auth/google" className="btn-secondary mt-6 w-full">
            <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden>
              <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
              <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
              <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
              <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
            </svg>
            Continue with Google
          </a>
        )}
        {linkSent ? (
          <div className="mt-6 rounded-xl bg-emerald-50 p-4 text-sm text-emerald-800 dark:bg-emerald-500/10 dark:text-emerald-200">
            Check your inbox: we sent a sign-in link to <b>{email}</b>.
          </div>
        ) : (
          <form onSubmit={submit} className="mt-6 space-y-4">
            {mode === "register" && (
              <div>
                <label className="label" htmlFor="name">Name</label>
                <input id="name" className="input" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
              </div>
            )}
            <div>
              <label className="label" htmlFor="email">Email</label>
              <input id="email" type="email" required className="input" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
            </div>
            <div>
              <label className="label" htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                required
                minLength={mode === "register" ? 8 : undefined}
                className="input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete={mode === "register" ? "new-password" : "current-password"}
              />
            </div>
            {error && <p role="alert" className="text-sm text-rose-600">{error}</p>}
            <button className="btn-primary w-full" disabled={busy}>
              {mode === "login" ? "Sign in" : "Create account"}
            </button>
            <button type="button" onClick={sendLink} className="btn-ghost w-full" disabled={busy}>
              <Mail className="h-4 w-4" /> Email me a sign-in link instead
            </button>
          </form>
        )}
        <p className="mt-6 text-center text-sm text-slate-500">
          {mode === "login" ? (
            <>New here? <Link href="/register" className="font-semibold text-brand-600">Create an account</Link></>
          ) : (
            <>Already have an account? <Link href="/login" className="font-semibold text-brand-600">Sign in</Link></>
          )}
        </p>
      </div>
    </div>
  );
}
