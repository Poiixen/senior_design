import { Fragment, useId, useState } from "react";
import { SortButton, type SortDirection } from "~/components/diagnostic-tables";
import {
  compareMeasurements,
  formatNumber,
  formatPercentage,
  type AnalysisReport,
  type CategoricalColumnProfile,
  type ColumnProfile,
  type NumericColumnProfile,
} from "~/lib/report";

type SortKey = "name" | "missing" | "unique";
type CategoryFilter = "all" | "numeric" | "categorical";

const SORT_LABELS: Record<SortKey, string> = { name: "Column", missing: "Missing %", unique: "Unique %" };
const FILTER_LABELS: Record<CategoryFilter, string> = { all: "All", numeric: "Numeric", categorical: "Categorical" };

function formatValue(value: CategoricalColumnProfile["most_common_value"]): string {
  if (value === null) return "Unavailable";
  return typeof value === "number" ? formatNumber(value) : String(value);
}

function PrimaryStatistic({ profile }: { profile: ColumnProfile }) {
  if (profile.category === "numeric") {
    return <>{profile.median === null ? "Unavailable" : `Median ${formatNumber(profile.median)}`}</>;
  }
  if (profile.most_common_value === null) return <>Unavailable</>;
  return (
    <>
      Most common: <span className="column-profile-value">{formatValue(profile.most_common_value)}</span>
      {" "}({formatPercentage(profile.most_common_percentage)})
    </>
  );
}

function NumericDetails({ profile }: { profile: NumericColumnProfile }) {
  const statistics: [string, number | null][] = [
    ["Mean", profile.mean],
    ["Median", profile.median],
    ["Standard deviation", profile.std_dev],
    ["Minimum", profile.min],
    ["Q1 (25th percentile)", profile.q1],
    ["Q3 (75th percentile)", profile.q3],
    ["Maximum", profile.max],
  ];
  return (
    <dl className="column-profile-stats">
      {statistics.map(([label, value]) => (
        <div key={label}><dt>{label}</dt><dd>{formatNumber(value)}</dd></div>
      ))}
    </dl>
  );
}

function CategoricalDetails({ profile }: { profile: CategoricalColumnProfile }) {
  return (
    <dl className="column-profile-stats">
      <div><dt>Most common value</dt><dd className="column-profile-value">{formatValue(profile.most_common_value)}</dd></div>
      <div><dt>Most common count</dt><dd>{formatNumber(profile.most_common_count)}</dd></div>
      <div><dt>Most common %</dt><dd>{formatPercentage(profile.most_common_percentage)}</dd></div>
    </dl>
  );
}

function ProfileDetails({ profile }: { profile: ColumnProfile }) {
  return (
    <div className="column-profile-detail">
      {profile.category === "numeric" ? <NumericDetails profile={profile} /> : <CategoricalDetails profile={profile} />}
      <dl className="column-profile-stats column-profile-stats-secondary">
        <div><dt>Storage type</dt><dd>{profile.dtype}</dd></div>
        <div><dt>Non-missing values</dt><dd>{formatNumber(profile.non_null_count)}</dd></div>
        <div><dt>Missing count</dt><dd>{formatNumber(profile.missing_count)}</dd></div>
      </dl>
      {profile.non_null_count === 0 && (
        <p className="muted">This column has no non-missing values, so its statistics are unavailable.</p>
      )}
    </div>
  );
}

function sortProfiles(profiles: ColumnProfile[], key: SortKey, direction: SortDirection): ColumnProfile[] {
  return [...profiles].sort((a, b) => {
    const byName = a.name.localeCompare(b.name);
    if (key === "name") return direction === "ascending" ? byName : -byName;
    const [first, second] = key === "missing"
      ? [a.missing_percentage, b.missing_percentage]
      : [a.unique_percentage, b.unique_percentage];
    return compareMeasurements(first, second, direction) || byName;
  });
}

export function ColumnProfileTable({ report }: { report: AnalysisReport }) {
  const profiles = report.column_profiles;
  const [filter, setFilter] = useState<CategoryFilter>("all");
  const [sort, setSort] = useState<{ key: SortKey; direction: SortDirection }>({ key: "name", direction: "ascending" });
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const idPrefix = useId();

  if (profiles == null) {
    return (
      <div className="diagnostics-content">
        <p className="notice notice-info">
          Column statistics are unavailable for this report. Reports saved before column profiling
          was added, or analyses stopped by structural errors, do not include them.
        </p>
      </div>
    );
  }

  const numericCount = profiles.filter((profile) => profile.category === "numeric").length;
  const categoricalCount = profiles.length - numericCount;
  const rows = sortProfiles(
    filter === "all" ? profiles : profiles.filter((profile) => profile.category === filter),
    sort.key,
    sort.direction,
  );

  const sortBy = (key: SortKey) => setSort((current) => current.key === key
    ? { key, direction: current.direction === "ascending" ? "descending" : "ascending" }
    : { key, direction: key === "name" ? "ascending" : "descending" });
  const toggleRow = (name: string) => setExpanded((current) => {
    const next = new Set(current);
    if (!next.delete(name)) next.add(name);
    return next;
  });
  const sortHeader = (key: SortKey) => (
    <th scope="col" aria-sort={sort.key === key ? sort.direction : undefined}>
      <SortButton label={SORT_LABELS[key]} direction={sort.direction} active={sort.key === key} onClick={() => sortBy(key)} />
    </th>
  );
  const emptyMessage = profiles.length === 0
    ? "No columns were profiled for this dataset."
    : filter === "numeric"
      ? "This dataset has no numeric columns."
      : "This dataset has no categorical columns.";

  return (
    <div className="diagnostics-content">
      <section className="panel diagnostic-summary" aria-label="Column profile summary">
        <div>
          <strong className="diagnostic-total">{formatNumber(profiles.length)}</strong>
          <p className="muted">
            Columns profiled · {formatNumber(numericCount)} numeric, {formatNumber(categoricalCount)} categorical
          </p>
        </div>
        <div className="report-filter" role="group" aria-label="Show column type">
          {(Object.keys(FILTER_LABELS) as CategoryFilter[]).map((option) => (
            <button key={option} type="button" aria-pressed={filter === option} onClick={() => setFilter(option)}>
              {FILTER_LABELS[option]}
            </button>
          ))}
        </div>
      </section>

      <div className="diagnostic-table-scroll" role="region" aria-label="Column profiles" tabIndex={0}>
        <table className="diagnostic-table column-profile-table">
          <caption className="report-sr-only">
            Type, missing percentage, unique values, and a primary statistic for each column. Expand a row for all statistics.
          </caption>
          <thead>
            <tr>
              {sortHeader("name")}
              <th scope="col">Type</th>
              {sortHeader("missing")}
              <th scope="col">Unique values</th>
              {sortHeader("unique")}
              <th scope="col">Primary statistic</th>
              <th scope="col"><span className="report-sr-only">Details</span></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((profile, index) => {
              const isOpen = expanded.has(profile.name);
              const detailId = `${idPrefix}-detail-${index}`;
              return (
                <Fragment key={profile.name}>
                  <tr className={isOpen ? "column-profile-open" : undefined}>
                    <th scope="row">{profile.name}</th>
                    <td><span className={`column-type column-type-${profile.category}`}>{FILTER_LABELS[profile.category]}</span></td>
                    <td>{formatPercentage(profile.missing_percentage)}</td>
                    <td>{formatNumber(profile.unique_values)}</td>
                    <td>{formatPercentage(profile.unique_percentage)}</td>
                    <td><PrimaryStatistic profile={profile} /></td>
                    <td>
                      <button
                        className="diagnostic-sort column-profile-toggle"
                        type="button"
                        aria-expanded={isOpen}
                        aria-controls={detailId}
                        onClick={() => toggleRow(profile.name)}
                      >
                        {isOpen ? "Hide" : "Details"}
                        <span className="report-sr-only"> for {profile.name}</span>
                      </button>
                    </td>
                  </tr>
                  {isOpen && (
                    <tr id={detailId} className="column-profile-detail-row">
                      <td colSpan={7}><ProfileDetails profile={profile} /></td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
            {rows.length === 0 && (
              <tr><td className="diagnostic-empty" colSpan={7}>{emptyMessage}</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="notice notice-info">
        Missing percentages use all rows; unique percentages use non-missing values. Numeric columns
        list their median, categorical columns their most common value. Open “Details” for every
        statistic; “Unavailable” means a measurement could not be calculated.
      </p>
    </div>
  );
}
