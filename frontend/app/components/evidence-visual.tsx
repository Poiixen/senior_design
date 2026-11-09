import type { ReactNode } from "react";
import type { NumericSummary, VisualSpec } from "~/lib/analysis";
import { formatNumber } from "~/lib/report";

const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const records = (v: unknown): Record<string, unknown>[] => Array.isArray(v) ? v.filter(x => x && typeof x === "object") : [];
const display = (v: unknown): string => v == null ? "Unavailable" : typeof v === "object" ? JSON.stringify(v) : String(v);

export function EvidenceTable({ data }: { data: Record<string, unknown> }) {
  const flatten = (value: unknown, path: string): [string, unknown][] => {
    if (Array.isArray(value)) return value.length ? value.flatMap((v, i) => flatten(v, `${path} · ${i + 1}`)) : [[path, "None"]];
    if (value && typeof value === "object") return Object.entries(value).flatMap(([k, v]) => flatten(v, [path, k.replaceAll("_", " ")].filter(Boolean).join(" · ")));
    return [[path, value]];
  };
  return <div className="diagnostic-table-scroll" tabIndex={0}><table className="diagnostic-table"><caption>Saved evidence values</caption><tbody>{flatten(data, "").map(([key, value], i) => <tr key={i}><th scope="row">{key}</th><td className="evidence-value">{display(value)}</td></tr>)}</tbody></table></div>;
}

export function Bars({ rows, unit = "" }: { rows: { label: string; value: number }[]; unit?: string }) {
  const low = Math.min(0, ...rows.map(r => r.value)), high = Math.max(0, ...rows.map(r => r.value));
  const scale = (n: number) => (n - low) / (high - low || 1) * 100;
  return <div className="evidence-bars" role="list">{rows.map((row, i) => <div className="evidence-bar-row" role="listitem" key={i}><span>{row.label}</span><div className="evidence-bar-track" aria-hidden="true"><i style={{ left: `${Math.min(scale(0), scale(row.value))}%`, width: `${Math.abs(scale(row.value) - scale(0))}%` }} /></div><strong>{formatNumber(row.value)} {unit}</strong></div>)}</div>;
}

export function CorrelationDetails({ data }: { data?: { columns: string[]; matrix: (number | null)[][] } }) {
  if (!data?.columns.length) return null;
  const { columns, matrix } = data;
  return <section className="panel relationship-explorer" id="correlation"><h2>Numerical correlations</h2><p>Saved Pearson correlations (−1 to 1). Missing values are excluded per pair. Pair sample sizes and row-level points were not saved; correlation does not establish causation.</p><div className="diagnostic-table-scroll" tabIndex={0}><table className="diagnostic-table"><caption>Correlation heatmap and accessible coefficient table · all saved numeric columns</caption><thead><tr><th>Column</th>{columns.map(c => <th key={c}>{c}</th>)}</tr></thead><tbody>{columns.map((c, i) => <tr key={c}><th scope="row">{c}</th>{columns.map((other, j) => { const value = matrix[i]?.[j]; return <td key={other} style={{ backgroundColor: finite(value) ? `rgba(${value < 0 ? "53,109,208" : "104,84,232"},${.08 + .4 * Math.abs(value)})` : undefined }}>{formatNumber(value)}</td>; })}</tr>)}</tbody></table></div></section>;
}

export function BoxPlot({ groups, label }: { groups: NumericSummary[]; label: string }) {
  if (!groups.length || groups.some(g => ![g.q1, g.median, g.q3].every(finite))) return <p className="notice notice-info">Box plot unavailable: saved quartiles or medians are missing. See the evidence table.</p>;
  const values = groups.flatMap(g => [g.min, g.whisker_low, g.q1, g.median, g.q3, g.whisker_high, g.max]).filter(finite);
  const low = Math.min(...values), high = Math.max(...values);
  const x = (n: number) => 25 + (n - low) / (high - low || 1) * 550;
  const hasWhiskers = groups.every(g => finite(g.whisker_low) && finite(g.whisker_high));
  return <div className="box-plots">{groups.map((g, i) => <div key={i}><p><strong>{String(g.label ?? label)}</strong> · n = {formatNumber(g.count)} · Median {formatNumber(g.median)} · Outliers {formatNumber(g.outlier_count)}</p><svg viewBox="0 0 600 70" role="img" aria-label={`${String(g.label ?? label)}: Q1 ${g.q1}, median ${g.median}, Q3 ${g.q3}; whiskers ${g.whisker_low ?? "unavailable"} to ${g.whisker_high ?? "unavailable"}`}>
    {finite(g.whisker_low) && finite(g.whisker_high) && <g stroke="currentColor"><line x1={x(g.whisker_low)} x2={x(g.whisker_high)} y1="25" y2="25" /><line x1={x(g.whisker_low)} x2={x(g.whisker_low)} y1="15" y2="35" /><line x1={x(g.whisker_high)} x2={x(g.whisker_high)} y1="15" y2="35" /></g>}
    <rect x={x(g.q1!)} y="10" width={Math.max(1, x(g.q3!) - x(g.q1!))} height="30" fill="var(--accent, #6854e8)" opacity=".35" stroke="currentColor" />
    <line x1={x(g.median!)} x2={x(g.median!)} y1="10" y2="40" stroke="currentColor" strokeWidth="3" />
    <text x="25" y="63">{formatNumber(low)}</text><text x="575" y="63" textAnchor="end">{formatNumber(high)}</text><text x="300" y="63" textAnchor="middle">{label}</text>
  </svg></div>)}<p className="muted">Boxes show Q1–Q3 with the median. {hasWhiskers ? "Whiskers reach the most extreme observed values within 1.5 × IQR of the quartiles; they are not confidence intervals." : "Actual whisker endpoints were not saved; only quartiles and medians are drawn."} Individual outlier points are unavailable; no points are sampled or invented.</p></div>;
}

export function EvidenceVisual({ spec }: { spec: VisualSpec }) {
  const d = spec.data ?? {};
  let chart: ReactNode = null;
  let reason = spec.fallback_reason;
  if (spec.chart_type === "bar" && Array.isArray(d.categories) && Array.isArray(d.values) && d.values.length === d.categories.length && d.values.every(finite)) {
    chart = <Bars rows={d.values.map((value, i) => ({ label: String((d.categories as unknown[])[i]), value: value as number }))} unit={spec.units ?? ""} />;
  } else if (spec.chart_type === "histogram" && Array.isArray(d.counts) && Array.isArray(d.bin_edges) && d.bin_edges.length === d.counts.length + 1 && d.counts.every(finite) && d.bin_edges.every(finite)) {
    const counts = d.counts as number[], edges = d.bin_edges as number[];
    const max = Math.max(1, ...counts), low = edges[0], high = edges.at(-1)!;
    const x = (n: number) => 45 + (n - low) / (high - low || 1) * 530;
    chart = <div className="profile-chart histogram-chart"><p>Included values: {formatNumber(counts.reduce((sum, n) => sum + n, 0))}. Bins include their lower endpoint; only the final bin includes its upper endpoint.</p><svg viewBox="0 0 600 210" role="img" aria-label={`Histogram of ${spec.x_label ?? spec.title}; bin counts are in the evidence table`}><line x1="45" y1="10" x2="45" y2="170" /><line x1="45" y1="170" x2="575" y2="170" />{counts.map((n, i) => <rect key={i} x={x(edges[i])} y={170 - 155 * n / max} width={Math.max(1, x(edges[i + 1]) - x(edges[i]) - 1)} height={155 * n / max}><title>{edges[i]} to {edges[i + 1]}: {n} rows</title></rect>)}<text x="45" y="190">{formatNumber(low)}</text><text x="575" y="190" textAnchor="end">{formatNumber(high)}</text><text x="300" y="207" textAnchor="middle">{spec.x_label}</text><text x="40" y="15" textAnchor="end">{max}</text></svg></div>;
  } else if (spec.chart_type === "grouped_box" || spec.chart_type === "box_plot") {
    const groups = spec.chart_type === "grouped_box" ? records(d.groups) : [d];
    if (groups.length && groups.every(g => [g.q1, g.median, g.q3].every(finite))) {
      chart = <BoxPlot groups={groups as unknown as NumericSummary[]} label={spec.y_label ?? spec.title} />;
    } else reason = "Box plot unavailable: saved quartiles or medians are missing. Available evidence is shown below.";
  } else if (spec.chart_type === "before_after_bar" && Array.isArray(d.before) && Array.isArray(d.after)) {
    const all = [...records(d.before), ...records(d.after)];
    if (all.every(r => finite(r.count))) chart = <Bars rows={all.map((r, i) => ({ label: `${i < (d.before as unknown[]).length ? "Before" : "After"}: ${String(r.label)}`, value: r.count as number }))} unit="rows" />;
  } else if (["grouped_percentage_bar", "contingency_heatmap"].includes(spec.chart_type) && Array.isArray(d.group_categories) && Array.isArray(d.outcome_categories) && Array.isArray(d.counts)) {
    const groups = d.group_categories, outcomes = d.outcome_categories, counts = d.counts as number[][];
    const percentages = d.row_percentages as number[][] | undefined;
    if (counts.length === groups.length && counts.every(row => Array.isArray(row) && row.length === outcomes.length && row.every(finite))) {
      const max = Math.max(1, ...counts.flat());
      chart = <div className="diagnostic-table-scroll" tabIndex={0}><table className="diagnostic-table"><caption>Contingency counts{percentages ? "; percentages use the group total (row sum)" : ""}</caption><thead><tr><th>Group (n)</th>{outcomes.map((o, i) => <th key={i}>{String(o)}</th>)}</tr></thead><tbody>{groups.map((g, i) => <tr key={i}><th scope="row">{String(g)} (n={counts[i].reduce((a, b) => a + b, 0)})</th>{outcomes.map((_, j) => <td key={j} style={{ backgroundColor: `rgba(104,84,232,${.08 + .4 * counts[i][j] / max})` }}>{counts[i][j]}{finite(percentages?.[i]?.[j]) && <span> · {formatNumber(percentages![i][j])}%</span>}</td>)}</tr>)}</tbody></table></div>;
    }
  } else if (spec.chart_type === "correlation_pair" && finite(d.value)) {
    chart = <div className="correlation-focus"><strong>{formatNumber(d.value)}</strong><p>{spec.x_label} ↔ {spec.y_label}</p><p>Saved correlation coefficient (−1 to 1). Association does not establish causation.</p></div>;
  }
  if (!chart && !reason) reason = "Chart evidence is unavailable or this visual type is not supported. Saved values are shown below.";
  return <figure className="evidence-visual"><figcaption><strong>{spec.title}</strong></figcaption><p className="muted">{[spec.x_label, spec.y_label, spec.units && `Units: ${spec.units}`, spec.percent_denominator && `Percentage denominator: ${spec.percent_denominator}`].filter(Boolean).join(" · ")}</p>{spec.warnings?.map((w, i) => <p className="notice notice-warning" key={i}>{w}</p>)}{spec.unavailable_fields?.length ? <p className="muted">Unavailable fields: {spec.unavailable_fields.join(", ")}</p> : null}{reason && <p className="notice notice-info">{reason}</p>}{chart}<details open={!chart}><summary>Accessible evidence table</summary><EvidenceTable data={d} /></details></figure>;
}
