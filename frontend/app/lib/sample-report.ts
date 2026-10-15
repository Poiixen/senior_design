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
  column_profiles: [
    {
      name: "age", dtype: "int64", category: "numeric",
      non_null_count: 20, missing_count: 0, missing_percentage: 0, unique_values: 16, unique_percentage: 80,
      mean: 31.2, median: 30.5, std_dev: 9.84, min: 19, q1: 23, q3: 38, max: 58,
    },
    {
      name: "score", dtype: "float64", category: "numeric",
      non_null_count: 20, missing_count: 0, missing_percentage: 0, unique_values: 15, unique_percentage: 75,
      mean: 17.1, median: 15, std_dev: 9.42, min: 4, q1: 10, q3: 20, max: 52,
    },
    {
      name: "empty_measurement", dtype: "float64", category: "numeric",
      non_null_count: 0, missing_count: 20, missing_percentage: 100, unique_values: 0, unique_percentage: null,
      mean: null, median: null, std_dev: null, min: null, q1: null, q3: null, max: null,
    },
    {
      name: "region", dtype: "object", category: "categorical",
      non_null_count: 18, missing_count: 2, missing_percentage: 10, unique_values: 4, unique_percentage: 22.22,
      most_common_value: "North", most_common_count: 7, most_common_percentage: 38.89,
    },
    {
      name: "group", dtype: "object", category: "categorical",
      non_null_count: 20, missing_count: 0, missing_percentage: 0, unique_values: 2, unique_percentage: 10,
      most_common_value: "treatment", most_common_count: 11, most_common_percentage: 55,
    },
  ],
  duplicates: {
    duplicate_count: 1,
    duplicate_percentage: 5,
    duplicate_group_count: 1,
    rows_in_duplicate_groups: 2,
    largest_duplicate_group_size: 2,
    duplicate_columns: ["age", "score"],
    repeated_value_summary: [
      { column_name: "age", repeated_values: 3, rows_affected: 7 },
      { column_name: "score", repeated_values: 2, rows_affected: 4 },
    ],
  },
  validation: {
    valid: true,
    errors: [],
    warnings: ["Column 'empty_measurement' contains only missing values."],
  },
  diagnostics: [],
};
