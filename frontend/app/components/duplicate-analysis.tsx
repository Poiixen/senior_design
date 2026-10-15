import { useState } from "react";
import { SortButton, type SortDirection } from "~/components/diagnostic-tables";
import { compareMeasurements, formatNumber, formatPercentage, type AnalysisReport } from "~/lib/report";

export function DuplicateAnalysis({ report }: { report: AnalysisReport }) {
  const [direction, setDirection] = useState<SortDirection>("descending");
  const toggleSort = () => setDirection((value) => value === "descending" ? "ascending" : "descending");
  const duplicates = report.duplicates;
  // Older reports carry only the summary count; every other measurement is unavailable.
  const duplicateRows = duplicates?.duplicate_count ?? report.summary.duplicate_rows;
  const repeatedSummary = duplicates?.repeated_value_summary;
  const rows = repeatedSummary && [...repeatedSummary].sort((a, b) =>
    compareMeasurements(a.rows_affected, b.rows_affected, direction) ||
    a.column_name.localeCompare(b.column_name),
  );

  const metrics: [string, string][] = [
    ["Duplicate rows", formatNumber(duplicateRows)],
    ["Duplicate %", formatPercentage(duplicates?.duplicate_percentage)],
    ["Duplicate groups", formatNumber(duplicates?.duplicate_group_count)],
    ["Rows in duplicate groups", formatNumber(duplicates?.rows_in_duplicate_groups)],
    ["Largest duplicate group", duplicates?.largest_duplicate_group_size == null
      ? "Unavailable"
      : `${formatNumber(duplicates.largest_duplicate_group_size)} rows`],
  ];

  return (
    <div className="diagnostics-content">
      <dl className="duplicate-metrics">
        {metrics.map(([label, value]) => (
          <div key={label} className="panel duplicate-metric"><dt>{label}</dt><dd>{value}</dd></div>
        ))}
      </dl>

      {duplicates == null && (
        <p className="notice notice-info">
          Detailed duplicate analysis is unavailable for this report. Only the duplicate-row count
          from the report summary is shown.
        </p>
      )}
      {duplicateRows === 0 && report.dataset.rows > 0 && (
        <p className="notice notice-success">No duplicate rows found. Every row in this dataset is distinct.</p>
      )}

      <section className="panel duplicate-columns" aria-labelledby="duplicate-columns-title">
        <h2 id="duplicate-columns-title">Columns with repeated values</h2>
        <p className="muted">
          Identifier-like columns (mostly distinct values) where some values appear in more than one row.
          These can reveal near-duplicate records that are not exact row copies.
        </p>
        {duplicates?.duplicate_columns == null ? (
          <p className="duplicate-columns-empty">Repeated-column information is unavailable for this report.</p>
        ) : duplicates.duplicate_columns.length === 0 ? (
          <p className="duplicate-columns-empty">No identifier-like columns contain repeated values.</p>
        ) : (
          <ul className="duplicate-column-list" aria-label="Columns with repeated values">
            {duplicates.duplicate_columns.map((column) => <li key={column}>{column}</li>)}
          </ul>
        )}
      </section>

      <div className="diagnostic-table-scroll" role="region" aria-label="Repeated-value summary" tabIndex={0}>
        <table className="diagnostic-table duplicate-repeated-table">
          <caption className="report-sr-only">Number of repeated values and rows affected for each identifier-like column.</caption>
          <thead>
            <tr>
              <th scope="col">Column</th>
              <th scope="col">Distinct values repeated</th>
              <th scope="col" aria-sort={direction}>
                <SortButton label="Rows affected" direction={direction} onClick={toggleSort} />
              </th>
            </tr>
          </thead>
          <tbody>
            {rows?.map((row) => (
              <tr key={row.column_name}>
                <th scope="row">{row.column_name}</th>
                <td>{formatNumber(row.repeated_values)}</td>
                <td>{formatNumber(row.rows_affected)}</td>
              </tr>
            ))}
            {(rows == null || rows.length === 0) && (
              <tr>
                <td className="diagnostic-empty" colSpan={3}>
                  {rows == null
                    ? "The repeated-value summary is unavailable for this report."
                    : "No repeated values were found in identifier-like columns."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="notice notice-info">
        Duplicate rows are exact copies of an earlier row; the first occurrence is not counted.
        A duplicate group is one distinct row together with all of its copies. Raw dataset rows are
        not stored, so individual duplicate records are not shown.
      </p>
    </div>
  );
}
