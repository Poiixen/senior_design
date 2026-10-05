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
    response = await fetch(url, init);
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
  return requestReport(origin ? new URL(path, origin).toString() : path, { signal });
}

export async function getReports(signal?: AbortSignal, origin?: string): Promise<ReportSummary[]> {
  const path = "/api/reports";
  const url = origin ? new URL(path, origin).toString() : `${apiBase}${path}`;
  let response: Response;
  try {
    response = await fetch(url, { signal });
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
