import { SignerPage } from "@/components/esign/SignerPage";

export const metadata = { title: "Sign a document", robots: { index: false, follow: false }, referrer: "no-referrer" };

export default async function SignPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <SignerPage token={token} />;
}
