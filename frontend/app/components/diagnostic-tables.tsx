import { useState } from "react";
import {
  compareMeasurements,
  formatNumber,
  formatPercentage,
  type AnalysisReport,
} from "~/lib/report";

type SortDirection = "ascending" | "descending";

function SortButton({
  label,
  direction,
  onClick,
}: {
  label: string;
  direction: SortDirection;
  onClick: () => void;
}) {
  return (
    <button className="diagnostic-sort" type="button" onClick={onClick}>
      {label} <span aria-hidden="true">{direction === "descending" ? "↓" : "↑"}</span>
      <span className="report-sr-only">
        {` (sorted ${direction}; activate to sort ${direction === "descending" ? "ascending" : "descending"})`}
      </span>
    </button>
  );
}

function Severity({ value }: { value: string | null | undefined }) {
  const severity = value?.toLowerCase() || "unavailable";
  const tone = ["low", "moderate", "medium", "high", "none"].includes(severity)
    ? severity
    : "unavailable";
  return (
    <span className={`diagnostic-severity diagnostic-severity-${tone}`}>
      {severity.charAt(0).toUpperCase() + severity.slice(1)}
    </span>
  );
}

export function MissingValueTable({ report }: { report: AnalysisReport }) {
  const [direction, setDirection] = useState<SortDirection>("descending");
  const toggleSort = () => setDirection((value) => value === "descending" ? "ascending" : "descending");
  const rows = [...report.missing_values].sort((a, b) =>
    compareMeasurements(a.missing_percentage, b.missing_percentage, direction) ||
    a.column_name.localeCompare(b.column_name),
  );

  return (
    <div className="diagnostics-content">
      <section className="panel diagnostic-summary" aria-label="Missing-value summary">
        <div>
          <strong className="diagnostic-total">{formatNumber(report.summary.missing_columns)}</strong>
          <p className="muted">Columns with missing data</p>
        </div>
        <SortButton label="Sort by: Missing %" direction={direction} onClick={toggleSort} />
      </section>

      {report.summary.missing_columns === 0 && report.dataset.rows > 0 && report.missing_values.length === 0 && (
        <p className="notice notice-success">No missing values detected in this dataset.</p>
      )}

      <div className="diagnostic-table-scroll" role="region" aria-label="Missing-value diagnostics" tabIndex={0}>
        <table className="diagnostic-table">
          <caption className="report-sr-only">Missing-value counts, percentages, and severity for each column.</caption>
          <thead>
            <tr>
              <th scope="col">Column</th>
              <th scope="col">Missing count</th>
              <th scope="col" aria-sort={direction}>
                <SortButton label="Missing %" direction={direction} onClick={toggleSort} />
              </th>
              <th scope="col">Severity</th>
              <th scope="col">Review</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.column_name}>
                <th scope="row">{row.column_name}</th>
                <td>{formatNumber(row.missing_count)}</td>
                <td>{formatPercentage(row.missing_percentage)}</td>
                <td><Severity value={row.severity} /></td>
                <td>{row.missing_count > 0 ? "Review suggested" : row.missing_percentage == null ? "Unavailable" : "No missing values"}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td className="diagnostic-empty" colSpan={5}>No column-level missing-value measurements are available.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="notice notice-info">
        Missing percentages use all rows in each column. A value of 0.00% means no missing
        values were found; “Unavailable” means a measurement could not be calculated.
      </p>
    </div>
  );
}

export function OutlierTable({ report }: { report: AnalysisReport }) {
  const [direction, setDirection] = useState<SortDirection>("descending");
  const toggleSort = () => setDirection((value) => value === "descending" ? "ascending" : "descending");
  const rows = [...report.outliers].sort((a, b) =>
    compareMeasurements(a.outlier_count, b.outlier_count, direction) ||
    a.column_name.localeCompare(b.column_name),
  );

  return (
    <div className="diagnostics-content">
      <section className="panel diagnostic-summary" aria-label="Outlier summary">
        <div>
          <strong className="diagnostic-total">{formatNumber(report.summary.outlier_columns)}</strong>
          <p className="muted">Columns with outliers</p>
        </div>
        <SortButton label="Sort by: Outlier count" direction={direction} onClick={toggleSort} />
      </section>

      {report.summary.outlier_columns === 0 && report.outliers.some((row) => row.outlier_percentage != null) && (
        <p className="notice notice-success">No outliers detected in numeric columns with available measurements.</p>
      )}

      <div className="diagnostic-table-scroll" role="region" aria-label="Outlier diagnostics" tabIndex={0}>
        <table className="diagnostic-table">
          <caption className="report-sr-only">Outlier counts, percentages, and interquartile range bounds for numeric columns.</caption>
          <thead>
            <tr>
              <th scope="col">Numeric column</th>
              <th scope="col" aria-sort={direction}>
                <SortButton label="Outlier count" direction={direction} onClick={toggleSort} />
              </th>
              <th scope="col">Outlier %</th>
              <th scope="col">Lower IQR bound</th>
              <th scope="col">Upper IQR bound</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.column_name}>
                <th scope="row">{row.column_name}</th>
                <td>{formatNumber(row.outlier_count)}</td>
                <td>{formatPercentage(row.outlier_percentage)}</td>
                <td>{formatNumber(row.lower_bound)}</td>
                <td>{formatNumber(row.upper_bound)}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td className="diagnostic-empty" colSpan={5}>
                  {report.summary.numeric_columns === 0
                    ? "This dataset has no numeric columns to check for outliers."
                    : "No numeric-column outlier measurements are available."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="notice notice-info">
        Outliers are values to review, not automatically incorrect data. Percentages use
        non-missing numeric values. IQR bounds mark the expected range; “Unavailable” means
        there were insufficient numeric values to calculate a measurement.
      </p>
    </div>
  );
}
