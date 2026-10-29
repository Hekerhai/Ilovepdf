import { WorkflowBuilder } from "@/components/WorkflowBuilder";

export const metadata = {
  title: "Workflows",
  description: "Chain PDF tools into one-click workflows: OCR, compress, watermark and protect hundreds of files at once.",
};

export default function WorkflowsPage() {
  return <WorkflowBuilder />;
}
