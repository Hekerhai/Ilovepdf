import { Cpu, ShieldCheck, Workflow, Zap } from "lucide-react";
import Link from "next/link";

import { ToolGrid } from "@/components/ToolGrid";
import { catalog } from "@/lib/tools";

const FEATURES = [
  {
    icon: ShieldCheck,
    title: "Private by default",
    text: "Merge, split, rotate, organize and convert images right in your browser. Those files never touch a server.",
  },
  {
    icon: Zap,
    title: "Fast",
    text: "No upload or queue for on-device tools. Server tools run on dedicated workers and stream results back.",
  },
  {
    icon: Workflow,
    title: "Batch workflows",
    text: "Chain tools like OCR → compress → watermark → protect, save the recipe, and run it on hundreds of files.",
  },
  {
    icon: Cpu,
    title: "Built for developers",
    text: "Every tool is available through a simple REST API with API keys, usage tracking and OpenAPI docs.",
  },
];

export default function Home() {
  return (
    <>
      <section className="relative overflow-hidden border-b border-slate-200 bg-gradient-to-b from-brand-50 to-slate-50 dark:border-slate-800 dark:from-slate-900 dark:to-slate-950">
        <div className="container-page py-16 text-center md:py-24">
          <span className="chip border-brand-200 bg-white text-brand-700 dark:border-brand-800 dark:bg-slate-900 dark:text-brand-300">
            <ShieldCheck className="h-3.5 w-3.5" /> Files auto-delete. Many tools never upload at all.
          </span>
          <h1 className="mx-auto mt-6 max-w-3xl text-4xl font-extrabold tracking-tight md:text-6xl">
            Every tool you need to work with PDFs
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-lg text-slate-600 dark:text-slate-400">
            {catalog.tools.length} tools to merge, split, compress, convert, sign, OCR, redact and summarize PDFs. Free to
            use, no watermarks, no ads.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link href="/tools/merge" className="btn-primary px-6 py-3 text-base">
              Merge PDFs
            </Link>
            <Link href="/tools/compress" className="btn-secondary px-6 py-3 text-base">
              Compress a PDF
            </Link>
          </div>
        </div>
      </section>

      <section className="container-page py-12">
        <ToolGrid />
      </section>

      <section className="container-page py-12">
        <h2 className="text-center text-3xl font-bold tracking-tight">Why people switch</h2>
        <div className="mt-10 grid gap-6 md:grid-cols-4">
          {FEATURES.map((f) => (
            <div key={f.title} className="card p-6">
              <f.icon className="h-6 w-6 text-brand-600" />
              <h3 className="mt-4 font-semibold">{f.title}</h3>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{f.text}</p>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
