export type Role = "owner" | "admin" | "analyst" | "viewer";
export type Session = {
  user: { id: string; email: string; display_name: string | null; email_verified: boolean };
  memberships: { organization_id: string; role: Role }[];
  csrf_token: string;
};
export type Organization = {
  id: string;
  name: string;
  slug: string;
  settings_version: number;
  settings: {
    amount_limits?: Record<string, string>;
    delay_window_days?: number;
  };
};
export type Page<T> = { items: T[]; next_cursor: string | null };
export type ImportBatch = {
  id: string;
  status: string;
  filename: string;
  row_count: number;
  error_count: number;
  job: { status: string; error_code: string | null } | null;
};
export type Audit = {
  id: string;
  status: string;
  rule_set_version: string;
  finding_count: number;
  limitation: string | null;
  import_ids: string[];
};
export type Evidence = {
  id: string;
  type: string;
  data: Record<string, unknown>;
};
export type Finding = {
  id: string;
  audit_id: string;
  rule_code: string;
  severity: string;
  review_state: string;
  detected_at: string;
  explanation: string;
  subject_key: string;
  subject_label: string;
  evidence: Evidence[];
};
export type Case = {
  id: string;
  finding_id: string;
  status: string;
  assignee_user_id: string | null;
  assignee_name?: string | null;
  closure_reason: string | null;
  opened_at: string;
  closed_at: string | null;
  comments?: Comment[];
  history?: Record<string, unknown>[];
};
export type Comment = {
  id: string;
  body: string;
  author_user_id: string;
  author_name?: string | null;
  created_at: string;
};
export type Analytics = {
  imports: number;
  analyzed_records: number;
  audits: number;
  findings_by_severity: Record<string, number>;
  pending_cases: number;
  resolved_cases: number;
  dismissed_cases: number;
  trend: { date: string; count: number }[];
  suppliers: { supplier_id: string; name: string; count: number }[];
  products: { product_id: string; name: string; count: number }[];
  limitations: string[];
};

let csrfToken = "";
export function setCsrfToken(token: string) {
  csrfToken = token;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (options.method && options.method !== "GET" && csrfToken)
    headers.set("X-CSRF-Token", csrfToken);
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as {
      message?: string;
    };
    throw new ApiError(
      response.status,
      payload.message || `Erro HTTP ${response.status}`,
    );
  }
  return response.status === 204
    ? (undefined as T)
    : (response.json() as Promise<T>);
}

export function json(
  method: "POST" | "PATCH",
  body: unknown,
  headers?: HeadersInit,
): RequestInit {
  return { method, body: JSON.stringify(body), headers };
}

export function query(params: Record<string, string | undefined>): string {
  const entries = Object.entries(params).filter(
    (entry): entry is [string, string] => Boolean(entry[1]),
  );
  const search = new URLSearchParams(entries).toString();
  return search ? `?${search}` : "";
}

export const orgPath = (id: string, path = "") => `/organizations/${id}${path}`;
