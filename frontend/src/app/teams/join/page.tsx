"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { useSession } from "@/components/AppProviders";
import { api } from "@/lib/api";

function Join() {
  const { user, loading, refresh } = useSession();
  const params = useSearchParams();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const token = params.get("token") ?? "";
  const here = `/teams/join?token=${encodeURIComponent(token)}`;

  if (loading) return null;
  if (!user)
    return (
      <div className="container-page py-24 text-center">
        <p className="mb-4">Sign in or create an account with the invited email to join the team.</p>
        <Link href={`/login?next=${encodeURIComponent(here)}`} className="btn-primary">Sign in</Link>{" "}
        <Link href={`/register?next=${encodeURIComponent(here)}`} className="btn-secondary">Create account</Link>
      </div>
    );
  return (
    <div className="container-page py-24 text-center">
      <button
        className="btn-primary"
        onClick={async () => {
          try {
            await api.joinTeam(token);
            await refresh();
            router.push("/teams");
          } catch (e) {
            setError((e as Error).message);
          }
        }}
      >
        Accept invitation
      </button>
      {error && <p className="mt-4 text-rose-600">{error}</p>}
    </div>
  );
}

export default function JoinPage() {
  return (
    <Suspense>
      <Join />
    </Suspense>
  );
}
