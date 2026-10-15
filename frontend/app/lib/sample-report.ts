import type { AnalysisReport } from "./report";

/** Illustrative fixture for UI review, never substituted for a missing saved report. */
export const sampleReport: AnalysisReport = {
  analysis_id: 0,
  filename: "example-survey.csv",
  status: "completed",
  started_at: "2026-10-03T14:00:00Z",
  completed_at: "2026-10-03T14:00:01Z",
  dataset: { rows: 20, columns: 5 },
  summary: {
    issues_detected: 5,
    numeric_columns: 3,
    categorical_columns: 2,
    duplicate_rows: 1,
    missing_columns: 2,
    outlier_columns: 1,
  },
  parsing_options: { delimiter: ",", has_header: true, missing_values: [] },
  missing_values: [
    { column_name: "age", missing_count: 0, missing_percentage: 0, severity: "none" },
    { column_name: "score", missing_count: 0, missing_percentage: 0, severity: "none" },
    { column_name: "empty_measurement", missing_count: 20, missing_percentage: 100, severity: "high" },
    { column_name: "region", missing_count: 2, missing_percentage: 10, severity: "moderate" },
    { column_name: "group", missing_count: 0, missing_percentage: 0, severity: "none" },
  ],
  outliers: [
    { column_name: "age", outlier_count: 0, outlier_percentage: 0, q1: 23, q3: 38, iqr: 15, lower_bound: 0.5, upper_bound: 60.5 },
    { column_name: "score", outlier_count: 2, outlier_percentage: 10, q1: 10, q3: 20, iqr: 10, lower_bound: -5, upper_bound: 35 },
    { column_name: "empty_measurement", outlier_count: 0, outlier_percentage: null, q1: null, q3: null, iqr: null, lower_bound: null, upper_bound: null },
  ],
  validation: {
    valid: true,
    errors: [],
    warnings: ["Column 'empty_measurement' contains only missing values."],
  },
  diagnostics: [],
};
