import { Suspense } from "react";

import { SharedFile } from "@/components/SharedFile";

export const metadata = { title: "Shared document", robots: { index: false, follow: false }, referrer: "no-referrer" };

export default async function SharedPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return (
    <Suspense>
      <SharedFile token={token} />
    </Suspense>
  );
}
