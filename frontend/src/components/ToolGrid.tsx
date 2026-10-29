"use client";

import { Search } from "lucide-react";
import { useMemo, useState } from "react";

import { POPULAR } from "@/lib/catalog";
import { catalog } from "@/lib/tools";

import { ToolCard } from "./ToolCard";

export function ToolGrid() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string>("all");

  const tools = useMemo(() => {
    const q = query.trim().toLowerCase();
    const rank = (id: string) => (POPULAR.includes(id) ? POPULAR.indexOf(id) : POPULAR.length);
    return catalog.tools
      .filter((t) => category === "all" || t.category === category)
      .filter((t) => !q || `${t.name} ${t.description} ${t.accepts.join(" ")}`.toLowerCase().includes(q))
      .sort((a, b) => rank(a.id) - rank(b.id));
  }, [query, category]);

  return (
    <div id="tools" className="scroll-mt-24">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="flex flex-wrap gap-2">
          {[{ id: "all", name: "All" }, ...catalog.categories].map((c) => (
            <button
              key={c.id}
              onClick={() => setCategory(c.id)}
              className={`chip px-4 py-1.5 text-sm transition ${
                category === c.id
                  ? "border-brand-600 bg-brand-600 text-white"
                  : "border-slate-200 bg-white text-slate-700 hover:border-brand-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
              }`}
            >
              {c.name}
            </button>
          ))}
        </div>
        <label className="relative md:w-72">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            className="input pl-9"
            placeholder={`Search ${catalog.tools.length} tools…`}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search tools"
          />
        </label>
      </div>
      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {tools.map((t) => (
          <ToolCard key={t.id} tool={t} />
        ))}
      </div>
      {!tools.length && <p className="mt-10 text-center text-slate-500">No tools match “{query}”.</p>}
    </div>
  );
}
