import Link from "next/link";

import { BRAND } from "@/lib/brand";
import { catalog } from "@/lib/tools";

import { Logo } from "./Logo";

export function Footer() {
  return (
    <footer className="mt-24 border-t border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
      <div className="container-page grid gap-10 py-12 md:grid-cols-5">
        <div className="md:col-span-1">
          <Logo />
          <p className="mt-3 text-sm text-slate-500">
            Every PDF tool, private by default. Files that need our servers are deleted automatically.
          </p>
        </div>
        {catalog.categories.slice(0, 3).map((cat) => (
          <div key={cat.id}>
            <h3 className="text-sm font-semibold">{cat.name}</h3>
            <ul className="mt-3 space-y-2 text-sm text-slate-500">
              {catalog.tools
                .filter((t) => t.category === cat.id)
                .slice(0, 6)
                .map((t) => (
                  <li key={t.id}>
                    <Link href={`/tools/${t.id}`} className="hover:text-brand-600">
                      {t.name}
                    </Link>
                  </li>
                ))}
            </ul>
          </div>
        ))}
        <div>
          <h3 className="text-sm font-semibold">{BRAND}</h3>
          <ul className="mt-3 space-y-2 text-sm text-slate-500">
            <li><Link href="/pricing" className="hover:text-brand-600">Pricing</Link></li>
            <li><Link href="/developers" className="hover:text-brand-600">Developer API</Link></li>
            <li><Link href="/workflows" className="hover:text-brand-600">Workflows</Link></li>
            <li><Link href="/privacy" className="hover:text-brand-600">Privacy & GDPR</Link></li>
            <li><Link href="/terms" className="hover:text-brand-600">Terms</Link></li>
          </ul>
        </div>
      </div>
      <div className="border-t border-slate-200 py-6 text-center text-xs text-slate-500 dark:border-slate-800">
        © {new Date().getFullYear()} {BRAND}. Built on open-source PDF engines.
      </div>
    </footer>
  );
}
