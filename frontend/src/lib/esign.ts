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
  signers: { name: string; email: string; status: SignerStatus; signed_at?: string | null; decline_reason?: string | null; has_code?: boolean }[];
};
export type RequestDetail = RequestSummary & {
  message: string | null;
  sequential: boolean;
  stamp_id: boolean;
  original_sha256: string;
  final_sha256: string | null;
  files_deleted: boolean;
  events: { kind: string; at: string; who: string | null; ip: string | null; detail: string | null }[];
};
export type SignerView = {
  needs_code: false;
  request: { title: string; message: string | null; file_name: string; status: RequestStatus; sender: string; expires_at: string };
  signer: { name: string; email: string; status: SignerStatus };
  fields: Omit<SignField, "signer">[];
  can_sign: boolean;
  final_available: boolean;
};
/** What a signer sees before entering the access code the sender gave them. */
export type LockedView = { needs_code: true; request: { title: string; sender: string }; signer: { name: string } };

export type TemplateSummary = { id: string; name: string; file_name: string; roles: string[]; sequential: boolean; field_count: number; created_at: string; updated_at: string };
export type Template = TemplateSummary & { fields: SignField[]; message: string | null };
export type SendDetails = {
  title: string;
  message: string;
  signers: { name: string; email: string; access_code?: string | null }[];
  fields: SignField[];
  sequential: boolean;
  expires_in_days: number;
  stamp_id: boolean;
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

async function pdf(path: string, name: string, headers?: HeadersInit): Promise<File> {
  const res = await fetch(path, { credentials: "same-origin", headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(body?.error?.message ?? "The document is not available.", res.status, "gone");
  }
  return new File([await res.blob()], name, { type: "application/pdf" });
}

const codeHeader = (code?: string): HeadersInit => (code ? { "X-Access-Code": code } : {});

export const esign = {
  send(file: File, details: SendDetails) {
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

  templates: () => call<{ templates: TemplateSummary[] }>("/api/esign/templates"),
  template: (id: string) => call<Template>(`/api/esign/templates/${id}`),
  templateDocument: (id: string, name: string) => pdf(`/api/esign/templates/${id}/document`, name),
  saveTemplate(file: File, details: { name: string; roles: string[]; fields: SignField[]; message: string; sequential: boolean }) {
    const form = new FormData();
    form.append("file", file, file.name);
    form.append("details", JSON.stringify(details));
    return call<TemplateSummary>("/api/esign/templates", { method: "POST", body: form });
  },
  renameTemplate: (id: string, name: string) => call<TemplateSummary>(`/api/esign/templates/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  removeTemplate: (id: string) => call<void>(`/api/esign/templates/${id}`, { method: "DELETE" }),

  view: (token: string, code?: string) => call<SignerView | LockedView>(`/api/esign/sign/${token}`, { headers: codeHeader(code) }),
  signerDocument: (token: string, name: string, code?: string) => pdf(`/api/esign/sign/${token}/document`, name, codeHeader(code)),
  signerDocumentUrl: (token: string, code?: string) => `/api/esign/sign/${token}/document${code ? `?code=${encodeURIComponent(code)}` : ""}`,
  sign: (token: string, body: { values: Record<string, string | boolean>; signature: string | null; initials: string | null; consent: boolean }, code?: string) =>
    call<{ status: string; request_status: RequestStatus }>(`/api/esign/sign/${token}`, { method: "POST", body: JSON.stringify(body), headers: codeHeader(code) }),
  decline: (token: string, reason: string, code?: string) =>
    call<{ status: string }>(`/api/esign/sign/${token}/decline`, { method: "POST", body: JSON.stringify({ reason }), headers: codeHeader(code) }),
};
