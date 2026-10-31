import { Suspense } from "react";

import { RequestView } from "@/components/esign/Requests";

export const metadata = { title: "Signature request", robots: { index: false } };

export default async function RequestPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <Suspense>
      <RequestView id={id} />
    </Suspense>
  );
}
