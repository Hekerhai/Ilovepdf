export type JsonSchema = {
  type?: string;
  title?: string;
  description?: string;
  default?: unknown;
  enum?: (string | number)[];
  const?: unknown;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  minLength?: number;
  maxLength?: number;
  items?: JsonSchema;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  anyOf?: JsonSchema[];
  allOf?: JsonSchema[];
  $ref?: string;
  $defs?: Record<string, JsonSchema>;
};

export type ToolInfo = {
  id: string;
  name: string;
  description: string;
  category: string;
  accepts: string[];
  min_files: number;
  max_files: number | null;
  premium: boolean;
  browser_capable: boolean;
  produces_pdf: boolean;
  options_schema: JsonSchema;
};

export type Category = { id: string; name: string };

export type Catalog = { categories: Category[]; tools: ToolInfo[] };

export type Step = { tool: string; options: Record<string, unknown> };

export type Job = {
  id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  steps: Step[];
  inputs: string[];
  input_bytes: number;
  output_name: string | null;
  output_bytes: number | null;
  output_count: number | null;
  error: string | null;
  error_code: string | null;
  created_at: string;
  finished_at: string | null;
  expires_at: string;
  files_deleted: boolean;
  download_url: string | null;
};

export type Plan = {
  id: string;
  name: string;
  max_file_mb: number;
  max_files_per_task: number;
  tasks_per_day: number | null;
  premium_tools: boolean;
  workflows: boolean;
  team_workspace: boolean;
  esign_requests_per_month: number | null;
};

export type User = {
  id: string;
  email: string;
  name: string | null;
  email_verified: boolean;
  has_password: boolean;
  google_linked: boolean;
  plan: Plan;
};

export type SessionInfo = { user: User | null; plan: Plan; tasks_today?: number };

export type PublicConfig = {
  brand_name: string;
  file_ttl_hours: number;
  google_sign_in: boolean;
  ai_available: boolean;
  payments: Record<string, boolean>;
};

export type Workflow = { id: string; name: string; steps: Step[]; team_id: string | null; owner_id: string; updated_at: string };

export type Team = {
  id: string;
  name: string;
  plan: string;
  seats: number;
  seats_used: number;
  role: "owner" | "admin" | "member";
  members?: { user_id: string; email: string; name: string | null; role: string }[];
  invitations?: { id: string; email: string; role: string; expires_at: string }[];
};

/** The outcome of running a tool, wherever it ran. */
export type ToolResult = {
  blob: Blob;
  name: string;
  where: "browser" | "server";
  job?: Job;
};
