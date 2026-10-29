import { PricingTable } from "@/components/PricingTable";

export const metadata = { title: "Pricing", description: "Free forever for everyday PDF work. Pro and Business for power users and teams." };

export default function PricingPage() {
  return (
    <div className="container-page py-16">
      <div className="mx-auto max-w-2xl text-center">
        <h1 className="text-4xl font-extrabold tracking-tight">Simple, fair pricing</h1>
        <p className="mt-3 text-slate-600 dark:text-slate-400">
          On-device tools are free and unlimited, always. Pay only when you need heavy server work, AI, workflows or a team.
        </p>
      </div>
      <PricingTable />
      <div className="mx-auto mt-16 grid max-w-4xl gap-6 md:grid-cols-2">
        {[
          ["Can I cancel any time?", "Yes. Cancel from your account and keep Pro until the end of the period you paid for."],
          ["Do you keep my files?", "No. Server-processed files are deleted automatically after a couple of hours, or instantly when you click delete."],
          ["Which payment methods?", "Cards worldwide through Stripe. UPI, cards and netbanking in India through Razorpay."],
          ["Is there a developer API?", "Every plan with an account gets API credits. Pro and Business include more each month."],
        ].map(([q, a]) => (
          <div key={q} className="card p-6">
            <h3 className="font-semibold">{q}</h3>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{a}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
