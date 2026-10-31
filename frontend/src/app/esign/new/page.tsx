"use client";

import Link from "next/link";

import { useSession } from "@/components/AppProviders";
import { SendWizard } from "@/components/esign/SendWizard";

export default function NewRequestPage() {
  const { user, loading } = useSession();
  if (loading) return null;
  if (!user)
    return (
      <div className="container-page py-16 text-center">
        <Link href="/login?next=/esign/new" className="btn-primary">
          Sign in to request signatures
        </Link>
      </div>
    );
  return <SendWizard />;
}
