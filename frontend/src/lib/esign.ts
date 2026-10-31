import { ApiError } from "./api";

export type FieldType = "signature" | "initials" | "date" | "name" | "text" | "checkbox";
export type SignField = {
  signer: number;
  type: FieldType;
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
  required: boolean;
  label?: string | null;
};
export type SignerStatus = "waiting" | "pending" | "viewed" | "signed" | "declined";
export type RequestStatus = "sent" | "completed" | "declined" | "cancelled" | "expired";

export type RequestSummary = {
  id: string;
  title: string;
  file_name: string;
  status: RequestStatus;
  created_at: string;
  completed_at: string | null;
  expires_at: string;
  signers: { name: string; email: string; status: SignerStatus; signed_at?: string | null; decline_reason?: string | null }[];
};
export type RequestDetail = RequestSummary & {
  message: string | null;
  sequential: boolean;
  original_sha256: string;
  final_sha256: string | null;
  files_deleted: boolean;
  events: { kind: string; at: string; who: string | null; ip: string | null; detail: string | null }[];
};
export type SignerView = {
  request: { title: string; message: string | null; file_name: string; status: RequestStatus; sender: string; expires_at: string };
  signer: { name: string; email: string; status: SignerStatus };
  fields: Omit<SignField, "signer">[];
  can_sign: boolean;
  final_available: boolean;
};

/** One colour per signer, used for their fields everywhere. */
export const SIGNER_COLOURS = ["#2563eb", "#db2777", "#059669", "#d97706", "#7c3aed", "#0891b2"];
export const signerColour = (i: number) => SIGNER_COLOURS[i % SIGNER_COLOURS.length];

export const FIELD_LABELS: Record<FieldType, string> = {
  signature: "Signature",
  initials: "Initials",
  date: "Date signed",
  name: "Full name",
  text: "Text",
  checkbox: "Checkbox",
};

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const res = await fetch(path, { ...init, headers, credentials: "same-origin" });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(body?.error?.message ?? `Request failed (${res.status})`, res.status, body?.error?.code ?? "error");
  return body as T;
}

async function pdf(path: string, name: string): Promise<File> {
  const res = await fetch(path, { credentials: "same-origin" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(body?.error?.message ?? "The document is not available.", res.status, "gone");
  }
  return new File([await res.blob()], name, { type: "application/pdf" });
}

export const esign = {
  send(file: File, details: { title: string; message: string; signers: { name: string; email: string }[]; fields: SignField[]; sequential: boolean; expires_in_days: number }) {
    const form = new FormData();
    form.append("file", file, file.name);
    form.append("details", JSON.stringify(details));
    return call<RequestDetail>("/api/esign/requests", { method: "POST", body: form });
  },
  list: () => call<{ requests: RequestSummary[] }>("/api/esign/requests"),
  get: (id: string) => call<RequestDetail>(`/api/esign/requests/${id}`),
  document: (id: string, name: string) => pdf(`/api/esign/requests/${id}/document`, name),
  documentUrl: (id: string) => `/api/esign/requests/${id}/document`,
  remind: (id: string) => call<RequestDetail>(`/api/esign/requests/${id}/remind`, { method: "POST" }),
  cancel: (id: string) => call<RequestDetail>(`/api/esign/requests/${id}/cancel`, { method: "POST" }),
  remove: (id: string) => call<void>(`/api/esign/requests/${id}`, { method: "DELETE" }),

  view: (token: string) => call<SignerView>(`/api/esign/sign/${token}`),
  signerDocument: (token: string, name: string) => pdf(`/api/esign/sign/${token}/document`, name),
  signerDocumentUrl: (token: string) => `/api/esign/sign/${token}/document`,
  sign: (token: string, body: { values: Record<string, string | boolean>; signature: string | null; initials: string | null; consent: boolean }) =>
    call<{ status: string; request_status: RequestStatus }>(`/api/esign/sign/${token}`, { method: "POST", body: JSON.stringify(body) }),
  decline: (token: string, reason: string) => call<{ status: string }>(`/api/esign/sign/${token}/decline`, { method: "POST", body: JSON.stringify({ reason }) }),
};
