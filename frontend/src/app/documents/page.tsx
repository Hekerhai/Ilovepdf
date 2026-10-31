import { DocumentsView } from "@/components/DocumentsView";

export const metadata = { title: "My documents", robots: { index: false } };

export default function DocumentsPage() {
  return <DocumentsView />;
}
