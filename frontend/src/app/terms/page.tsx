import { BRAND } from "@/lib/brand";

export const metadata = { title: "Terms" };

export default function TermsPage() {
  return (
    <article className="container-page max-w-3xl space-y-5 py-12 text-slate-700 dark:text-slate-300">
      <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Terms of service</h1>
      <p>
        This is a placeholder. Replace it with terms drafted for your company and jurisdiction before launching {BRAND}.
      </p>
      <p>
        Topics to cover: acceptable use (only process documents you have the right to), fair-use limits on unlimited plans,
        subscription billing and refunds, API usage, service availability, liability and governing law.
      </p>
    </article>
  );
}
