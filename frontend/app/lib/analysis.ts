import { ApiError, requestJson, type CategoricalComparison, type ComparisonMethod } from "./api";

export type Category = string | number | boolean;
export type Mapping = { label: string; categories: Category[] };
export interface EvidenceRef { result_type: string; analysis_id: number; comparison_id?: number | null; column?: string | null }
export interface VisualSpec {
  chart_type: string; title: string; data: Record<string, unknown>; source?: EvidenceRef;
  x_label?: string | null; y_label?: string | null; units?: string | null;
  percent_denominator?: string | null; warnings?: string[]; unavailable_fields?: string[]; fallback_reason?: string | null;
}
export interface NumericSummary {
  label?: Category; count: number; mean: number | null; median: number | null; std_dev: number | null;
  min: number | null; q1: number | null; q3: number | null; max: number | null;
  whisker_low?: number | null; whisker_high?: number | null; outlier_count?: number | null;
}
interface ComparisonExtras {
  identifier_review?: { column: string; reasons: string[]; confirmed: boolean }[];
  regrouping?: {
    mappings: Record<string, Mapping[]>; original_comparison_id?: number | null; note: string;
    columns: { column: string; before: { label: Category; count: number }[]; after: { label: Category; count: number }[]; categories_before: number; categories_after: number }[];
    method_change: { explanation: string; group_count_before: number; group_count_after: number; method_before: string; method_after: string; changed: boolean };
  };
}
export interface NumericComparison extends ComparisonExtras {
  comparison_id: number; analysis_id: number; created_at: string; comparison_type: "categorical_numeric";
  selection: { group_column: string; value_column: string }; status: string; reason?: string | null;
  rows: { total: number; included: number; excluded: number; exclusion_reasons: Record<string, number> };
  groups?: NumericSummary[]; overall?: NumericSummary; warnings: string[]; note: string;
  analysis_question?: { key: string; text: string }; method_selection?: { rule: string };
  test: { method: ComparisonMethod & { limitations?: string[] }; status: string; reason?: string | null;
    statistic?: number; statistic_name?: string; degrees_of_freedom?: number; degrees_of_freedom_within?: number; p_value?: number;
    mean_difference?: number; difference_order?: Category[];
    mean_difference_ci?: { level: number; lower: number; upper: number; calculation: string } };
}
export type Comparison = (CategoricalComparison & ComparisonExtras) | NumericComparison;
export interface ComparisonRequest {
  comparison_type: "categorical_numeric" | "categorical_categorical"; group_column: string;
  value_column?: string; outcome_column?: string; method?: string;
  category_mappings?: Record<string, Mapping[]>; confirm_columns?: string[];
}
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
function validComparison(v: unknown, id: number): v is Comparison {
  return object(v) && v.analysis_id === id && typeof v.comparison_id === "number" &&
    ["categorical_numeric", "categorical_categorical"].includes(String(v.comparison_type)) && object(v.selection) &&
    object(v.rows) && object(v.test) && object(v.test.method) && Array.isArray(v.warnings);
}
export async function listComparisons(id: number, signal?: AbortSignal): Promise<Comparison[]> {
  const body = await requestJson(`/api/reports/${id}/comparisons`, { signal });
  if (!object(body) || !Array.isArray(body.comparisons) || !body.comparisons.every(v => validComparison(v, id))) throw new ApiError("Invalid saved comparison list.");
  return body.comparisons;
}
export async function createComparison(id: number, selection: ComparisonRequest, signal?: AbortSignal): Promise<Comparison> {
  const body = await requestJson(`/api/reports/${id}/comparisons`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(selection), signal });
  if (!validComparison(body, id)) throw new ApiError("Invalid comparison response.");
  return body;
}
export function evidenceHref(ref: EvidenceRef): string {
  if (ref.comparison_id != null) return `?view=columns&comparison=${ref.comparison_id}#comparison-${ref.comparison_id}`;
  if (ref.result_type === "correlation") return "?view=columns#correlation";
  const view = ref.result_type.includes("missing") ? "missing" : ref.result_type.includes("duplicate") ? "duplicates" : ref.result_type.includes("outlier") ? "outliers" : "columns";
  return `?view=${view}`;
}

export interface ChatMessage { message_id: number; role: "user" | "assistant"; content: string; request_id: string; status?: string; sources: { source_id: string; label: string; comparison_id?: number | null }[] }
export interface Conversation { conversation_id: number; first_question?: string | null }
export interface History { analysis_id: number; conversation_id: number; messages: ChatMessage[] }
export interface Question { question: string; request_id: string; conversation_id?: number }
export interface Answer { analysis_id: number; conversation_id: number; status: string; user_message: ChatMessage; assistant_message?: ChatMessage | null; unavailable_reason?: string }
export interface DuplicatePreview { analysis_id: number; original_rows: number; proposed_removed_rows: number; resulting_rows: number; definition: string; note: string }
// Every report-scoped response must match the active report, even if a proxy returns a late response.
export async function reportRequest<T extends { analysis_id: number }>(id: number, suffix: string, signal: AbortSignal, body?: unknown): Promise<T> {
  const result = await requestJson(`/api/reports/${id}/${suffix}`, { signal, ...(body !== undefined ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}) });
  if (!object(result) || result.analysis_id !== id) throw new ApiError("The response does not belong to this report.");
  return result as unknown as T;
}
