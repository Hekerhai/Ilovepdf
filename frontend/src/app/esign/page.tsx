import { RequestList } from "@/components/esign/Requests";

export const metadata = {
  title: "Request signatures",
  description: "Send a PDF to anyone for signature, track who has signed, and get a sealed copy with an audit trail.",
};

export default function ESignPage() {
  return <RequestList />;
}
