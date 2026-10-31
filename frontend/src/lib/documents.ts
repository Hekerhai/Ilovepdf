import { ApiError } from "./api";

export type Doc = { id: string; name: string; size: number; content_type: string; created_at: string; updated_at: string };
export type Share = {
  id: string;
  url: string;
  embed: string;
  has_password: boolean;
  allow_download: boolean;
  expires_at: string | null;
  max_downloads: number | null;
  downloads: number;
  views: number;
  sent_to: string | null;
  created_at: string;
};
export type Shared = {
  name: string;
  size: number;
  content_type: string;
  shared_by: string;
  needs_password: boolean;
  allow_download: boolean;
  expires_at: string | null;
  grant: string | null;
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

export const documents = {
  list: () => call<{ documents: Doc[]; usage: { used_bytes: number; limit_bytes: number } }>("/api/documents"),
  upload(files: (File | { blob: Blob; name: string })[]) {
    const form = new FormData();
    for (const f of files) {
      if (f instanceof File) form.append("files", f, f.name);
      else form.append("files", f.blob, f.name);
    }
    return call<{ documents: Doc[] }>("/api/documents", { method: "POST", body: form });
  },
  fromJob: (jobId: string) => call<Doc>(`/api/documents/from-job/${jobId}`, { method: "POST" }),
  fileUrl: (id: string, download = false) => `/api/documents/${id}/file${download ? "?download=true" : ""}`,
  rename: (id: string, name: string) => call<Doc>(`/api/documents/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  remove: (id: string) => call<void>(`/api/documents/${id}`, { method: "DELETE" }),
  shares: (id: string) => call<{ shares: Share[] }>(`/api/documents/${id}/shares`),
  share: (id: string, body: { expires_in_days?: number | null; password?: string | null; max_downloads?: number | null; allow_download?: boolean }) =>
    call<Share>(`/api/documents/${id}/shares`, { method: "POST", body: JSON.stringify(body) }),
  revoke: (id: string, shareId: string) => call<void>(`/api/documents/${id}/shares/${shareId}`, { method: "DELETE" }),
  send: (id: string, body: { email: string; message?: string; expires_in_days?: number }) =>
    call<Share>(`/api/documents/${id}/send`, { method: "POST", body: JSON.stringify(body) }),

  shared: (token: string) => call<Shared>(`/api/s/${token}`),
  unlock: (token: string, password: string) => call<{ grant: string }>(`/api/s/${token}/unlock`, { method: "POST", body: JSON.stringify({ password }) }),
  sharedFileUrl: (token: string, grant: string, download = false) =>
    `/api/s/${token}/file?grant=${encodeURIComponent(grant)}${download ? "&download=true" : ""}`,
};
