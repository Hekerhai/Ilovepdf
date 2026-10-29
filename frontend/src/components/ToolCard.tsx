import { Crown, ShieldCheck } from "lucide-react";
import Link from "next/link";

import { CATEGORY_STYLES, fallbackIcon, TOOL_ICONS } from "@/lib/catalog";
import type { ToolInfo } from "@/lib/types";

export function ToolIcon({ tool, size = "md" }: { tool: ToolInfo; size?: "md" | "lg" }) {
  const Icon = TOOL_ICONS[tool.id] ?? fallbackIcon;
  const style = CATEGORY_STYLES[tool.category];
  const box = size === "lg" ? "h-14 w-14 rounded-2xl" : "h-11 w-11 rounded-xl";
  return (
    <span className={`inline-flex shrink-0 items-center justify-center ${box} ${style?.bg} ${style?.text}`}>
      <Icon className={size === "lg" ? "h-7 w-7" : "h-5 w-5"} />
    </span>
  );
}

export function ToolCard({ tool }: { tool: ToolInfo }) {
  return (
    <Link
      href={`/tools/${tool.id}`}
      className="card group relative flex flex-col gap-3 p-5 transition hover:-translate-y-0.5 hover:border-brand-300 hover:shadow-lift"
    >
      <div className="flex items-start justify-between">
        <ToolIcon tool={tool} />
        <div className="flex gap-1">
          {tool.browser_capable && (
            <span title="Runs in your browser" className="chip border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-500/10">
              <ShieldCheck className="h-3 w-3" /> On-device
            </span>
          )}
          {tool.premium && (
            <span title="Pro" className="chip border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-500/10">
              <Crown className="h-3 w-3" /> Pro
            </span>
          )}
        </div>
      </div>
      <div>
        <h3 className="font-semibold group-hover:text-brand-700 dark:group-hover:text-brand-300">{tool.name}</h3>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{tool.description}</p>
      </div>
    </Link>
  );
}
