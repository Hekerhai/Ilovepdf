"use client";

import { Crown, LogOut, Menu, User as UserIcon, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { api } from "@/lib/api";

import { useSession } from "./AppProviders";
import { Logo } from "./Logo";

const NAV = [
  { href: "/#tools", label: "All tools" },
  { href: "/workflows", label: "Workflows" },
  { href: "/esign", label: "eSign" },
  { href: "/developers", label: "API" },
  { href: "/pricing", label: "Pricing" },
];

export function Header() {
  const { user, plan, loading, refresh } = useSession();
  const [open, setOpen] = useState(false);
  const router = useRouter();

  async function signOut() {
    await api.logout();
    await refresh();
    router.push("/");
  }

  const premium = plan?.premium_tools;

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200/70 bg-white/80 backdrop-blur dark:border-slate-800 dark:bg-slate-950/80">
      <div className="container-page flex h-16 items-center justify-between gap-4">
        <div className="flex items-center gap-8">
          <Logo />
          <nav className="hidden items-center gap-1 md:flex">
            {NAV.map((n) => (
              <Link key={n.href} href={n.href} className="btn-ghost px-3 py-2">
                {n.label}
              </Link>
            ))}
          </nav>
        </div>
        <div className="hidden items-center gap-2 md:flex">
          {loading ? null : user ? (
            <>
              {!premium && (
                <Link href="/pricing" className="btn-secondary px-3 py-2">
                  <Crown className="h-4 w-4 text-amber-500" /> Upgrade
                </Link>
              )}
              <Link href="/account" className="btn-ghost px-3 py-2">
                <UserIcon className="h-4 w-4" /> {user.name || user.email}
                {premium && <span className="chip border-amber-300 bg-amber-50 text-amber-700">{plan?.name}</span>}
              </Link>
              <button onClick={signOut} className="btn-ghost px-3 py-2" aria-label="Sign out">
                <LogOut className="h-4 w-4" />
              </button>
            </>
          ) : (
            <>
              <Link href="/login" className="btn-ghost">
                Sign in
              </Link>
              <Link href="/register" className="btn-primary">
                Sign up free
              </Link>
            </>
          )}
        </div>
        <button className="btn-ghost md:hidden" onClick={() => setOpen(!open)} aria-label="Menu">
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>
      {open && (
        <div className="border-t border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-950 md:hidden">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} className="block py-2" onClick={() => setOpen(false)}>
              {n.label}
            </Link>
          ))}
          {user ? (
            <>
              <Link href="/account" className="block py-2" onClick={() => setOpen(false)}>
                Account
              </Link>
              <button onClick={signOut} className="block py-2 text-left">
                Sign out
              </button>
            </>
          ) : (
            <Link href="/login" className="block py-2" onClick={() => setOpen(false)}>
              Sign in
            </Link>
          )}
        </div>
      )}
    </header>
  );
}
