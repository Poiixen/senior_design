import { Fragment, useEffect, useId, useRef, useState } from "react";
import { useRevalidator } from "react-router";
import { SortButton, type SortDirection } from "~/components/diagnostic-tables";
import { ApiError, saveColumnDisplayNames } from "~/lib/api";
import {
  compareMeasurements,
  columnDisplayName,
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

function InlineColumnName({ report, sourceName }: { report: AnalysisReport; sourceName: string }) {
  const revalidator = useRevalidator();
  const displayName = columnDisplayName(report, sourceName);
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(displayName);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => { setValue(displayName); }, [displayName]);
  useEffect(() => { if (editing) inputRef.current?.select(); }, [editing]);

  if (report.parsing_options.has_header) return <>{sourceName}</>;
  const cancel = () => { setValue(displayName); setEditing(false); setError(""); };
  const save = async () => {
    const name = value.trim();
    if (!name || name === displayName || saving) { if (name === displayName) setEditing(false); return; }
    const names = Object.fromEntries((report.column_profiles ?? []).map((profile) => [
      profile.name,
      profile.name === sourceName ? name : columnDisplayName(report, profile.name),
    ]));
    setSaving(true); setError("");
    try { await saveColumnDisplayNames(report.analysis_id, names); setEditing(false); await revalidator.revalidate(); }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : "Name could not be saved."); }
    finally { setSaving(false); }
  };

  if (!editing) return <button className="inline-column-name" type="button" title={`Edit ${displayName}`} onClick={() => setEditing(true)}><span>{displayName}</span><span aria-hidden="true">✎</span><span className="report-sr-only">Edit column name</span></button>;
  return <div className="inline-column-editor"><input ref={inputRef} aria-label={`Display name for ${sourceName}`} value={value} maxLength={100} disabled={saving} onChange={(event) => { setValue(event.target.value); setError(""); }} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); void save(); } if (event.key === "Escape") cancel(); }} /><div><button type="button" disabled={saving || !value.trim()} onClick={() => void save()}>{saving ? "Saving…" : "Save"}</button><button type="button" disabled={saving} onClick={cancel}>Cancel</button></div>{error && <span role="alert">{error}</span>}</div>;
}

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

function NumericDetails({ profile, displayName }: { profile: NumericColumnProfile; displayName: string }) {
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
    <>
      <dl className="column-profile-stats">
        {statistics.map(([label, value]) => (
          <div key={label}><dt>{label}</dt><dd>{formatNumber(value)}</dd></div>
        ))}
      </dl>
      <Histogram profile={profile} displayName={displayName} />
    </>
  );
}

function Histogram({ profile, displayName }: { profile: NumericColumnProfile; displayName: string }) {
  const histogram = profile.histogram;
  if (!histogram) return <p className="notice notice-info">Histogram data is unavailable for this older report.</p>;
  if (histogram.included_values === 0 || histogram.counts.length === 0) return <p className="notice notice-info">No usable finite numeric values are available for a histogram.</p>;
  const width = 640, height = 220, left = 48, bottom = 42, top = 12, right = 12;
  const plotWidth = width - left - right, plotHeight = height - top - bottom;
  const maximum = Math.max(...histogram.counts, 1);
  const barWidth = plotWidth / histogram.counts.length;
  return (
    <figure className="profile-chart histogram-chart">
      <figcaption><strong>Distribution histogram</strong><span>{formatNumber(histogram.included_values)} usable numeric values included</span></figcaption>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Histogram of ${displayName} by count`}>
        <line x1={left} y1={top} x2={left} y2={height - bottom} /><line x1={left} y1={height - bottom} x2={width - right} y2={height - bottom} />
        {histogram.counts.map((count, index) => {
          const barHeight = (count / maximum) * plotHeight;
          return <rect key={index} x={left + index * barWidth + 1} y={height - bottom - barHeight} width={Math.max(1, barWidth - 2)} height={barHeight} rx="2"><title>{formatNumber(histogram.bin_edges[index])} to {formatNumber(histogram.bin_edges[index + 1])}: {count}</title></rect>;
        })}
        <text x={left} y={height - 20}>{formatNumber(histogram.bin_edges[0])}</text><text textAnchor="end" x={width - right} y={height - 20}>{formatNumber(histogram.bin_edges.at(-1))}</text>
        <text className="chart-axis-title" textAnchor="middle" x={left + plotWidth / 2} y={height - 2}>{displayName}</text>
        <text className="chart-axis-title" textAnchor="middle" transform={`translate(13 ${top + plotHeight / 2}) rotate(-90)`}>Count</text>
      </svg>
    </figure>
  );
}

const PIE_COLORS = ["#6854e8", "#356dd0", "#18a47b", "#e5a12b", "#d75a76", "#7d6b91", "#52a7c2"];
function CategoryPie({ profile }: { profile: CategoricalColumnProfile }) {
  const categories = profile.distribution?.categories ?? [];
  if (categories.length === 0) return null;
  const visible = categories.slice(0, 6);
  const shownCount = visible.reduce((sum, category) => sum + category.count, 0);
  const otherCount = Math.max(0, profile.distribution!.non_missing_rows - shownCount);
  const slices = [...visible, ...(otherCount ? [{ label: "Other", count: otherCount, percentage: otherCount / profile.distribution!.non_missing_rows * 100 }] : [])];
  let angle = -Math.PI / 2;
  const point = (value: number) => `${100 + 82 * Math.cos(value)},${100 + 82 * Math.sin(value)}`;
  return (
    <figure className="profile-chart category-chart">
      <figcaption><strong>Category share</strong><span>Small categories are grouped only in this chart; the table remains complete.</span></figcaption>
      <div className="category-chart-layout"><svg viewBox="0 0 200 200" role="img" aria-label={`Pie chart of ${profile.name} categories`}>
        {slices.map((slice, index) => { const start = angle; const delta = (slice.count / profile.distribution!.non_missing_rows) * Math.PI * 2; angle += delta; const end = angle; const path = slices.length === 1 ? undefined : `M 100,100 L ${point(start)} A 82,82 0 ${delta > Math.PI ? 1 : 0},1 ${point(end)} Z`; return slices.length === 1 ? <circle key={String(slice.label)} cx="100" cy="100" r="82" fill={PIE_COLORS[index % PIE_COLORS.length]}><title>{String(slice.label)}: {formatPercentage(slice.percentage)}</title></circle> : <path key={String(slice.label)} d={path} fill={PIE_COLORS[index % PIE_COLORS.length]}><title>{String(slice.label)}: {formatPercentage(slice.percentage)}</title></path>; })}
      </svg><ul>{slices.map((slice, index) => <li key={String(slice.label)}><i style={{ backgroundColor: PIE_COLORS[index % PIE_COLORS.length] }} />{String(slice.label)} <strong>{formatPercentage(slice.percentage)}</strong></li>)}</ul></div>
    </figure>
  );
}

function CategoricalDetails({ profile }: { profile: CategoricalColumnProfile }) {
  const distribution = profile.distribution;
  if (!distribution) return <p className="notice notice-info">Complete category distribution data is unavailable for this older report.</p>;
  return (
    <>
      <dl className="column-profile-stats">
        <div><dt>Distinct categories</dt><dd>{formatNumber(distribution.distinct_categories)}</dd></div>
        <div><dt>Non-missing rows</dt><dd>{formatNumber(distribution.non_missing_rows)}</dd></div>
        <div><dt>Missing rows</dt><dd>{formatNumber(distribution.missing_rows)}</dd></div>
        <div><dt>Total rows</dt><dd>{formatNumber(distribution.total_rows)}</dd></div>
      </dl>
      <div className="category-detail-grid">
        <div className="diagnostic-table-scroll"><table className="diagnostic-table category-distribution-table"><caption>Complete category distribution, ordered by descending count.</caption><thead><tr><th scope="col">Category</th><th scope="col">Count</th><th scope="col">Percentage</th></tr></thead><tbody>{distribution.categories.map((category) => <tr key={`${typeof category.label}-${String(category.label)}`}><th scope="row">{String(category.label)}</th><td>{formatNumber(category.count)}</td><td>{formatPercentage(category.percentage)}</td></tr>)}</tbody></table></div>
        <CategoryPie profile={profile} />
      </div>
      <p className="muted">Category percentages use {formatNumber(distribution.non_missing_rows)} non-missing rows as the denominator; missing rows are excluded.</p>
      {distribution.categories_truncated && <p className="notice notice-warning">The table shows the first {formatNumber(distribution.categories.length)} categories. {formatNumber(distribution.omitted_categories)} categories ({formatNumber(distribution.omitted_count)} values) were omitted because profiles are limited to 500 categories.</p>}
    </>
  );
}

function ProfileDetails({ profile, displayName }: { profile: ColumnProfile; displayName: string }) {
  return (
    <div className="column-profile-detail">
      {profile.category === "numeric" ? <NumericDetails profile={profile} displayName={displayName} /> : <CategoricalDetails profile={profile} />}
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
              const displayName = columnDisplayName(report, profile.name);
              const detailId = `${idPrefix}-detail-${index}`;
              return (
                <Fragment key={profile.name}>
                  <tr className={isOpen ? "column-profile-open" : undefined}>
                    <th scope="row"><InlineColumnName report={report} sourceName={profile.name} />{displayName !== profile.name && <small className="column-source-name">Source: {profile.name}</small>}</th>
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
                      <td colSpan={7}><ProfileDetails profile={profile} displayName={displayName} /></td>
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
