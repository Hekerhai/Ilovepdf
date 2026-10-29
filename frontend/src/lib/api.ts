import type { Catalog, Job, PublicConfig, SessionInfo, Step, Team, Workflow } from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(path, { ...init, headers, credentials: "same-origin" });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const body = text ? JSON.parse(text) : {};
  if (!res.ok) {
    const err = body?.error ?? {};
    throw new ApiError(err.message ?? `Request failed (${res.status})`, res.status, err.code ?? "error");
  }
  return body as T;
}

const json = (body: unknown) => JSON.stringify(body);

export const api = {
  config: () => request<PublicConfig>("/api/config"),
  tools: () => request<Catalog>("/api/tools"),
  session: () => request<SessionInfo>("/api/auth/session"),

  register: (email: string, password: string, name?: string) =>
    request<{ user: SessionInfo["user"] }>("/api/auth/register", { method: "POST", body: json({ email, password, name }) }),
  login: (email: string, password: string) =>
    request<{ user: SessionInfo["user"] }>("/api/auth/login", { method: "POST", body: json({ email, password }) }),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  logoutAll: () => request<void>("/api/auth/logout-all", { method: "POST" }),
  magicLink: (email: string) => request<void>("/api/auth/magic-link", { method: "POST", body: json({ email }) }),
  verifyMagicLink: (token: string) =>
    request<{ user: SessionInfo["user"] }>("/api/auth/magic-link/verify", { method: "POST", body: json({ token }) }),

  createJob(files: File[], steps: Step[]): Promise<Job> {
    const form = new FormData();
    files.forEach((f) => form.append("files", f, f.name));
    form.append("steps", json(steps));
    return request<Job>("/api/jobs", { method: "POST", body: form });
  },
  job: (id: string) => request<Job>(`/api/jobs/${id}`),
  jobs: () => request<{ jobs: Job[] }>("/api/jobs"),
  deleteJob: (id: string) => request<void>(`/api/jobs/${id}`, { method: "DELETE" }),
  async download(job: Job): Promise<Blob> {
    const res = await fetch(job.download_url!, { credentials: "same-origin" });
    if (!res.ok) throw new ApiError("The file is no longer available.", res.status, "gone");
    return res.blob();
  },

  updateProfile: (name: string) => request<void>("/api/me", { method: "PATCH", body: json({ name }) }),
  changePassword: (current_password: string | null, new_password: string) =>
    request<void>("/api/me/password", { method: "POST", body: json({ current_password, new_password }) }),
  deleteAccount: () => request<void>("/api/me", { method: "DELETE" }),
  apiKeys: () =>
    request<{
      usage: { used: number; included: number };
      keys: { id: string; name: string; prefix: string; created_at: string; last_used_at: string | null }[];
    }>("/api/me/api-keys"),
  createApiKey: (name: string) =>
    request<{ id: string; key: string }>("/api/me/api-keys", { method: "POST", body: json({ name }) }),
  revokeApiKey: (id: string) => request<void>(`/api/me/api-keys/${id}`, { method: "DELETE" }),

  workflows: () => request<{ workflows: Workflow[] }>("/api/workflows"),
  saveWorkflow: (name: string, steps: Step[], team_id?: string | null, id?: string) =>
    request<Workflow>(id ? `/api/workflows/${id}` : "/api/workflows", {
      method: id ? "PUT" : "POST",
      body: json({ name, steps, team_id: team_id || null }),
    }),
  deleteWorkflow: (id: string) => request<void>(`/api/workflows/${id}`, { method: "DELETE" }),

  teams: () => request<{ teams: Team[] }>("/api/teams"),
  team: (id: string) => request<Team>(`/api/teams/${id}`),
  createTeam: (name: string) => request<Team>("/api/teams", { method: "POST", body: json({ name }) }),
  invite: (teamId: string, email: string, role: string) =>
    request<Team>(`/api/teams/${teamId}/invitations`, { method: "POST", body: json({ email, role }) }),
  revokeInvite: (teamId: string, id: string) =>
    request<void>(`/api/teams/${teamId}/invitations/${id}`, { method: "DELETE" }),
  setRole: (teamId: string, userId: string, role: string) =>
    request<Team>(`/api/teams/${teamId}/members/${userId}`, { method: "PUT", body: json({ role }) }),
  removeMember: (teamId: string, userId: string) =>
    request<void>(`/api/teams/${teamId}/members/${userId}`, { method: "DELETE" }),
  joinTeam: (token: string) => request<Team>("/api/teams/join", { method: "POST", body: json({ token }) }),

  plans: () => request<BillingCatalog>("/api/billing/plans"),
  checkout: (body: { plan: string; interval: string; provider: string; seats?: number; team_id?: string }) =>
    request<{ provider: string; url: string | null; client_payload: Record<string, string> | null }>(
      "/api/billing/checkout",
      { method: "POST", body: json(body) },
    ),
  subscriptions: () =>
    request<{
      subscriptions: {
        id: string;
        plan: string;
        provider: string;
        status: string;
        seats: number;
        owner_type: string;
        current_period_end: string | null;
      }[];
    }>("/api/billing/subscriptions"),
  cancelSubscription: (id: string) => request<void>(`/api/billing/subscriptions/${id}/cancel`, { method: "POST" }),
};

export type BillingCatalog = {
  providers: { id: string; currency: string; configured: boolean }[];
  plans: {
    id: string;
    name: string;
    max_file_mb: number;
    max_files_per_task: number;
    tasks_per_day: number | null;
    premium_tools: boolean;
    team_workspace: boolean;
    monthly_api_credits: number;
    per_seat: boolean;
    min_seats: number;
    highlights: string[];
    prices: Record<string, { usd: number; inr: number }>;
  }[];
};

/** Poll a server job until it finishes. */
export async function waitForJob(id: string, onUpdate?: (job: Job) => void, signal?: AbortSignal): Promise<Job> {
  let delay = 400;
  for (;;) {
    if (signal?.aborted) throw new DOMException("Cancelled", "AbortError");
    const job = await api.job(id);
    onUpdate?.(job);
    if (job.status === "succeeded" || job.status === "failed") return job;
    await new Promise((r) => setTimeout(r, delay));
    delay = Math.min(delay * 1.5, 3000);
  }
}
