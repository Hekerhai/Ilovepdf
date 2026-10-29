"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { useSession } from "@/components/AppProviders";
import { api } from "@/lib/api";

function Verify() {
  const params = useSearchParams();
  const router = useRouter();
  const { refresh } = useSession();
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const token = params.get("token");
    if (!token) {
      setError("This link is incomplete.");
      return;
    }
    api
      .verifyMagicLink(token)
      .then(refresh)
      .then(() => router.replace("/account"))
      .catch((e) => setError(e.message));
  }, [params, refresh, router]);

  return (
    <div className="container-page py-24 text-center">
      {error ? <p className="text-rose-600">{error}</p> : <p className="text-slate-500">Signing you in…</p>}
    </div>
  );
}

export default function MagicPage() {
  return (
    <Suspense>
      <Verify />
    </Suspense>
  );
}
