/** The complete report returned by POST /api/analyze and GET /api/reports/:id. */
export interface ParsingOptions {
  delimiter: string;
  has_header: boolean;
  missing_values: string[];
}

export interface MissingValueResult {
  column_name: string;
  missing_count: number;
  missing_percentage: number | null;
  severity: string;
}

export interface OutlierResult {
  column_name: string;
  outlier_count: number;
  outlier_percentage: number | null;
  q1: number | null;
  q3: number | null;
  iqr: number | null;
  lower_bound: number | null;
  upper_bound: number | null;
}

/** Fields the backend profiler reports for every column. */
interface ColumnProfileBase {
  name: string;
  dtype: string;
  non_null_count: number;
  missing_count: number;
  missing_percentage: number | null;
  unique_values: number;
  unique_percentage: number | null;
}

export interface NumericColumnProfile extends ColumnProfileBase {
  category: "numeric";
  mean: number | null;
  median: number | null;
  std_dev: number | null;
  min: number | null;
  q1: number | null;
  q3: number | null;
  max: number | null;
}

export interface CategoricalColumnProfile extends ColumnProfileBase {
  category: "categorical";
  most_common_value: string | number | boolean | null;
  most_common_count: number | null;
  most_common_percentage: number | null;
}

export type ColumnProfile = NumericColumnProfile | CategoricalColumnProfile;

export interface RepeatedValueSummary {
  column_name: string;
  repeated_values: number;
  rows_affected: number;
}

/** Duplicate-row analysis. Group-level fields are absent from reports saved before they existed. */
export interface DuplicateAnalysisResult {
  duplicate_count: number;
  duplicate_percentage: number | null;
  duplicate_group_count?: number;
  rows_in_duplicate_groups?: number;
  largest_duplicate_group_size?: number;
  duplicate_columns?: string[];
  repeated_value_summary?: RepeatedValueSummary[];
}

export interface AnalysisReport {
  analysis_id: number;
  filename: string;
  status: "completed" | "running" | "failed";
  started_at: string;
  completed_at: string | null;
  dataset: { rows: number; columns: number };
  summary: {
    issues_detected: number;
    numeric_columns: number;
    categorical_columns: number;
    duplicate_rows: number;
    missing_columns: number;
    outlier_columns: number;
  };
  parsing_options: ParsingOptions;
  missing_values: MissingValueResult[];
  outliers: OutlierResult[];
  /** Null or absent when profiling did not run or the report predates column profiles. */
  column_profiles?: ColumnProfile[] | null;
  /** Null or absent when profiling did not run or the report predates duplicate details. */
  duplicates?: DuplicateAnalysisResult | null;
  validation: { valid: boolean; errors: string[]; warnings: string[] };
  diagnostics: ({ type: string } & Record<string, unknown>)[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isCount(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function isMeasurement(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isFinite(value));
}

function isPercentage(value: unknown): value is number | null {
  return isMeasurement(value) && (value === null || (value >= 0 && value <= 100));
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((entry) => typeof entry === "string");
}

function isTimestamp(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && Number.isFinite(Date.parse(value));
}

function isColumnProfile(value: unknown): value is ColumnProfile {
  if (!isRecord(value) || typeof value.name !== "string" || typeof value.dtype !== "string" ||
      !isCount(value.non_null_count) || !isCount(value.missing_count) || !isPercentage(value.missing_percentage) ||
      !isCount(value.unique_values) || !isPercentage(value.unique_percentage)) return false;
  if (value.category === "numeric") {
    return ["mean", "median", "std_dev", "min", "q1", "q3", "max"].every((key) => isMeasurement(value[key]));
  }
  return value.category === "categorical" &&
    (value.most_common_value === null || ["string", "number", "boolean"].includes(typeof value.most_common_value)) &&
    (value.most_common_count === null || isCount(value.most_common_count)) &&
    isPercentage(value.most_common_percentage);
}

function isDuplicateAnalysis(value: unknown): value is DuplicateAnalysisResult {
  return isRecord(value) && isCount(value.duplicate_count) && isPercentage(value.duplicate_percentage) &&
    ["duplicate_group_count", "rows_in_duplicate_groups", "largest_duplicate_group_size"]
      .every((key) => value[key] === undefined || isCount(value[key])) &&
    (value.duplicate_columns === undefined || isStringArray(value.duplicate_columns)) &&
    (value.repeated_value_summary === undefined || (Array.isArray(value.repeated_value_summary) &&
      value.repeated_value_summary.every((entry) =>
        isRecord(entry) && typeof entry.column_name === "string" &&
        isCount(entry.repeated_values) && isCount(entry.rows_affected),
      )));
}

/** Validate persisted API reports before any nested fields reach the interface. */
export function isAnalysisReport(value: unknown): value is AnalysisReport {
  if (!isRecord(value) || !isCount(value.analysis_id) || value.analysis_id === 0 ||
      typeof value.filename !== "string" ||
      typeof value.status !== "string" || !["completed", "running", "failed"].includes(value.status) ||
      !isTimestamp(value.started_at) ||
      !(value.completed_at === null || isTimestamp(value.completed_at))) return false;

  const { dataset, summary, parsing_options: options, validation } = value;
  if (!isRecord(dataset) || !isCount(dataset.rows) || !isCount(dataset.columns) ||
      !isRecord(summary) ||
      !["issues_detected", "numeric_columns", "categorical_columns", "duplicate_rows", "missing_columns", "outlier_columns"]
        .every((key) => isCount(summary[key])) ||
      !isRecord(options) || typeof options.delimiter !== "string" || options.delimiter.length !== 1 ||
      typeof options.has_header !== "boolean" || !isStringArray(options.missing_values) ||
      !isRecord(validation) || typeof validation.valid !== "boolean" ||
      !isStringArray(validation.errors) || !isStringArray(validation.warnings)) return false;

  return Array.isArray(value.missing_values) && value.missing_values.every((entry) =>
    isRecord(entry) && typeof entry.column_name === "string" &&
    isCount(entry.missing_count) && isPercentage(entry.missing_percentage) &&
    typeof entry.severity === "string",
  ) && Array.isArray(value.outliers) && value.outliers.every((entry) =>
    isRecord(entry) && typeof entry.column_name === "string" &&
    isCount(entry.outlier_count) && isPercentage(entry.outlier_percentage) &&
    ["q1", "q3", "iqr", "lower_bound", "upper_bound"].every((key) => isMeasurement(entry[key])),
  ) && (value.column_profiles == null ||
    (Array.isArray(value.column_profiles) && value.column_profiles.every(isColumnProfile))
  ) && (value.duplicates == null || isDuplicateAnalysis(value.duplicates)
  ) && Array.isArray(value.diagnostics) && value.diagnostics.every((entry) =>
    isRecord(entry) && typeof entry.type === "string",
  );
}

export function formatNumber(value: number | null | undefined): string {
  return value != null && Number.isFinite(value)
    ? new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 }).format(value)
    : "Unavailable";
}

export function formatPercentage(value: number | null | undefined): string {
  return value != null && Number.isFinite(value) ? `${value.toFixed(2)}%` : "Unavailable";
}

/** Missing measurements sort last in either direction; zero remains a real value. */
export function compareMeasurements(
  first: number | null | undefined,
  second: number | null | undefined,
  direction: "ascending" | "descending",
): number {
  const firstAvailable = first != null && Number.isFinite(first);
  const secondAvailable = second != null && Number.isFinite(second);
  if (!firstAvailable) return secondAvailable ? 1 : 0;
  if (!secondAvailable) return -1;
  return direction === "ascending" ? first - second : second - first;
}
