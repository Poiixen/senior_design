import { isAnalysisReport, type AnalysisReport, type ParsingOptions } from "./report";

export type ReportSummary = Pick<
  AnalysisReport,
  "analysis_id" | "filename" | "status" | "started_at" | "completed_at" | "dataset" | "summary"
>;

export const DEFAULT_PARSING_OPTIONS: ParsingOptions = {
  delimiter: ",",
  has_header: true,
  missing_values: [],
};

export class ApiError extends Error {
  status: number;
  constructor(message: string, status = 0) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const apiBase = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

export interface AuthUser { id: number; email: string }

function detailMessage(body: unknown): string | undefined {
  if (!body || typeof body !== "object" || !("detail" in body)) return;
  if (typeof body.detail === "string") return body.detail.trim() || undefined;
  if (Array.isArray(body.detail)) {
    return body.detail.map((item: unknown) =>
      item !== null && typeof item === "object" && "msg" in item && typeof item.msg === "string"
        ? item.msg
        : "Invalid request field.",
    ).join(" ") || undefined;
  }
}

async function requestReport(path: string, init?: RequestInit): Promise<AnalysisReport> {
  let response: Response;
  try {
    const url = /^https?:\/\//i.test(path) ? path : `${apiBase}${path}`;
    response = await fetch(url, { credentials: "include", ...init });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new ApiError("We couldn't reach the analysis service. Check that the backend is running, then try again.");
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(detailMessage(body) ?? (response.status === 404
      ? "This report could not be found. Check the report link or analyze your dataset again."
      : response.status >= 500 ? "The analysis service could not complete the request. Please try again."
      : "The dataset could not be analyzed. Check the file and parsing options, then try again."), response.status);
  }
  if (!isAnalysisReport(body)) {
    throw new ApiError("The analysis service returned an incomplete report. Please try again.", response.status);
  }
  return body;
}

export async function analyzeDataset(file: File, options: ParsingOptions, signal?: AbortSignal): Promise<AnalysisReport> {
  const form = new FormData();
  form.append("file", file);
  form.append("delimiter", options.delimiter);
  form.append("has_header", String(options.has_header));
  form.append("missing_values", JSON.stringify(options.missing_values));
  // The browser supplies the multipart Content-Type boundary.
  return requestReport("/api/analyze", { method: "POST", body: form, signal });
}

export function getReport(analysisId: string, signal?: AbortSignal, origin?: string): Promise<AnalysisReport> {
  const path = `/api/reports/${encodeURIComponent(analysisId)}`;
  const base = apiBase || origin;
  return requestReport(base ? new URL(path, base).toString() : path, { signal });
}

export async function getReports(signal?: AbortSignal, origin?: string): Promise<ReportSummary[]> {
  const path = "/api/reports";
  const base = apiBase || origin;
  const url = base ? new URL(path, base).toString() : path;
  let response: Response;
  try {
    response = await fetch(url, { signal, credentials: "include" });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new ApiError("We couldn't retrieve saved reports. Check that the backend is running, then try again.");
  }

  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(detailMessage(body) ?? "Saved reports could not be retrieved.", response.status);
  }
  if (!body || typeof body !== "object" || !("reports" in body) || !Array.isArray(body.reports)) {
    throw new ApiError("The analysis service returned an invalid report list.", response.status);
  }
  return body.reports as ReportSummary[];
}

async function authRequest(path: string, init?: RequestInit): Promise<AuthUser | null> {
  let response: Response;
  try {
    response = await fetch(`${apiBase}/api/auth/${path}`, { credentials: "include", ...init });
  } catch {
    throw new ApiError("We couldn't reach the authentication service. Check that the backend is running.");
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(detailMessage(body) ?? "The account request could not be completed.", response.status);
  if (path === "logout") return null;
  if (!body || typeof body !== "object" || !("id" in body) || !("email" in body) ||
      typeof body.id !== "number" || typeof body.email !== "string") {
    throw new ApiError("The authentication service returned an invalid response.", response.status);
  }
  return body as AuthUser;
}

const jsonRequest = (email: string, password: string): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email, password }),
});

export function registerUser(email: string, password: string) { return authRequest("register", jsonRequest(email, password)) as Promise<AuthUser>; }
export function loginUser(email: string, password: string) { return authRequest("login", jsonRequest(email, password)) as Promise<AuthUser>; }
export function logoutUser() { return authRequest("logout", { method: "POST" }); }
export function getCurrentUser() { return authRequest("me") as Promise<AuthUser>; }
