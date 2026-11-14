export interface PlatformJobCount {
  platform: string;
  category: string;
  connector_key: string;
  jobs_count: number;
}

export interface StatsResponse {
  total_required_platforms: number;
  verified_platforms: number;
  implemented_platforms: number;
  total_registered_sources: number;
  active_sources: number;
  total_companies: number;
  indexed_jobs: number;
  active_jobs: number;
  possibly_closed_jobs: number;
  closed_jobs: number;
  duplicate_groups: number;
  pending_duplicate_reviews: number;
  total_ingestion_runs: number;
  successful_ingestion_runs: number;
  failed_ingestion_runs: number;
  last_successful_refresh: string | null;
  jobs_by_platform: PlatformJobCount[];
  jobs_by_workplace: { workplace_type: string; count: number }[];
}

export interface JobSummary {
  id: string;
  canonical_job_key: string;
  title: string;
  company_id: string;
  company_name: string;
  department: string | null;
  location_raw: string | null;
  city: string | null;
  region: string | null;
  country: string | null;
  country_code: string | null;
  salary_raw: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  salary_period: string | null;
  employment_type: string;
  workplace_type: string;
  primary_source_url: string;
  primary_application_url: string;
  original_posted_at: string | null;
  first_seen_at: string;
  last_seen_at: string;
  last_checked_at: string | null;
  status: string;
  source_count: number;
  platforms: string[];
  platform_names?: string[];
  snippet?: string | null;
}

export interface SourceProvenance {
  source_id: string;
  source_name: string;
  source_url: string;
  platform_key: string | null;
  platform_name: string | null;
  external_job_id: string;
  source_job_url: string;
  application_url: string;
  is_active_on_source: boolean;
  missing_runs_count: number;
  first_seen_at: string;
  last_seen_at: string;
}

export interface JobChangeItem {
  id: string;
  job_id?: string;
  job_title?: string;
  company_name?: string;
  change_type: string;
  changed_fields: Record<string, { old: unknown; new: unknown }>;
  previous_hash: string | null;
  new_hash: string | null;
  detected_at: string;
}

export interface JobDetail extends JobSummary {
  description: string;
  description_text: string;
  employment_type_raw: string | null;
  workplace_type_raw: string | null;
  last_modified_at: string;
  closed_at: string | null;
  content_hash: string;
  sources: SourceProvenance[];
  changes: JobChangeItem[];
}

export interface SearchFacetBucket {
  value: string;
  count: number;
}

export interface SearchResponse {
  items: JobSummary[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  backend_used: string;
  latency_ms: number;
  facets: Record<string, SearchFacetBucket[]>;
}

export interface CompanySummary {
  id: string;
  name: string;
  normalized_name: string;
  website_url: string | null;
  active_jobs_count: number;
  sources_count: number;
  created_at: string;
}

export interface SourceItem {
  id: string;
  source_name: string;
  source_url: string;
  board_token: string | null;
  canonical_domain: string;
  source_type: string;
  status: string;
  priority: string;
  refresh_interval_minutes: number;
  discovery_method: string;
  discovery_confidence: number;
  company_id: string | null;
  company_name: string | null;
  platform_id: string | null;
  platform_name: string | null;
  platform_key: string | null;
  platform_category: string | null;
  active_jobs_count: number;
  consecutive_failures: number;
  last_checked_at: string | null;
  last_successful_sync_at: string | null;
  next_sync_at: string | null;
}

export interface PlatformCoverageEntry {
  id: string;
  name: string;
  category: string;
  connector_key: string;
  implementation_status: string;
  discovery_method: string;
  extraction_method: string;
  auth_requirements: string;
  pagination_support: boolean;
  rate_limit_rpm: number;
  last_successful_run: string | null;
  last_failed_run: string | null;
  sources_discovered: number;
  jobs_indexed: number;
  active_jobs: number;
  failed_requests: number;
  health_status: string;
  average_response_time_ms: number | null;
  verification_evidence: {
    verified_at: string;
    verification_run_id: string | null;
    example_source_url: string;
    jobs_verified_count: number;
    sample_job_title: string | null;
    sample_job_url: string | null;
  } | null;
  known_limitations: string | null;
  documentation_url: string | null;
  connector_registered_in_code?: boolean;
}

export interface CoverageReport {
  generated_at: string;
  total_required_platforms: number;
  status_summary: Record<string, number>;
  category_breakdown: Record<
    string,
    { total: number; verified: number; implemented: number }
  >;
  platforms: PlatformCoverageEntry[];
}

const ADMIN_KEY_STORAGE = "jobre_admin_api_key";

export function getStoredAdminKey(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(ADMIN_KEY_STORAGE) || "";
}

export function setStoredAdminKey(key: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ADMIN_KEY_STORAGE, key.trim());
}

export function clearStoredAdminKey(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(ADMIN_KEY_STORAGE);
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(path, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const err = await res.json();
      if (err?.detail) detail = String(err.detail);
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export async function adminFetch<T>(
  path: string,
  options: RequestInit = {},
  explicitKey?: string
): Promise<T> {
  const key = explicitKey ?? getStoredAdminKey();
  const headers = new Headers(options.headers || {});
  headers.set("Accept", "application/json");
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (key) {
    headers.set("X-Admin-Key", key);
  }
  const res = await fetch(path, {
    ...options,
    headers,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const err = await res.json();
      if (err?.detail) detail = String(err.detail);
    } catch {
      // ignore
    }
    const error = new Error(detail) as Error & { status?: number };
    error.status = res.status;
    throw error;
  }
  return res.json() as Promise<T>;
}

export function formatSalary(job: {
  salary_raw?: string | null;
  salary_min?: number | null;
  salary_max?: number | null;
  salary_currency?: string | null;
  salary_period?: string | null;
}): string | null {
  if (job.salary_min != null || job.salary_max != null) {
    const cur = job.salary_currency || "USD";
    const fmt = (n: number) =>
      new Intl.NumberFormat("en-US", {
        maximumFractionDigits: 0,
      }).format(n);
    const period = job.salary_period
      ? ` / ${job.salary_period.toLowerCase().replace("yearly", "yr").replace("hourly", "hr").replace("monthly", "mo")}`
      : "";
    if (job.salary_min != null && job.salary_max != null && job.salary_min !== job.salary_max) {
      return `${cur} ${fmt(job.salary_min)} – ${fmt(job.salary_max)}${period}`;
    }
    const val = job.salary_min ?? job.salary_max ?? 0;
    return `${cur} ${fmt(val)}${period}`;
  }
  if (job.salary_raw && job.salary_raw.trim()) {
    return job.salary_raw.trim();
  }
  return null;
}

export function formatDateShort(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function formatDateTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatEnumLabel(val?: string | null): string {
  if (!val) return "Unknown";
  return val
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
