import { BRAND } from "@/lib/brand";

export const metadata = { title: "Privacy & GDPR" };

export default function PrivacyPage() {
  return (
    <article className="container-page prose-sm max-w-3xl space-y-5 py-12 text-slate-700 dark:text-slate-300">
      <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Privacy & GDPR</h1>
      <p>
        {BRAND} is designed to need as little of your data as possible. This page explains what we process and why. Have your
        legal adviser review it before launch and add your company details as the data controller.
      </p>
      <h2 className="text-xl font-semibold">On-device processing</h2>
      <p>Tools marked “On-device” run in your browser. Those files are never uploaded and we never see them.</p>
      <h2 className="text-xl font-semibold">Server processing</h2>
      <p>
        Files sent to our servers are used only to perform the task you asked for. Inputs and results are deleted automatically
        a few hours after processing (or immediately when you click “Delete from server now”). Task records (tool, file names,
        sizes, status) are kept for 30 days for your history and abuse prevention, then deleted.
      </p>
      <h2 className="text-xl font-semibold">Accounts</h2>
      <p>
        We store your email, name, plan and a hash of your password (Argon2). Guests are identified by a random cookie and a
        salted hash of their IP address to apply the free limits. We use no advertising or third-party tracking cookies.
      </p>
      <h2 className="text-xl font-semibold">Payments</h2>
      <p>Payments are handled by Stripe or Razorpay. We never see or store your card details.</p>
      <h2 className="text-xl font-semibold">AI features</h2>
      <p>When you use an AI tool, the document text is sent to the configured AI provider solely to produce your answer.</p>
      <h2 className="text-xl font-semibold">Your rights</h2>
      <p>
        From your account you can export all data we hold about you (access and portability) and delete your account and
        data permanently (erasure). For anything else, contact us.
      </p>
    </article>
  );
}
