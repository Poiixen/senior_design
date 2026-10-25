import { useEffect, useRef, useState } from "react";
import { ApiError, compareCategoricalColumns, type CategoricalComparison } from "~/lib/api";
import { columnDisplayName, formatNumber, formatPercentage, type AnalysisReport } from "~/lib/report";

const label = (value: string | number | boolean) => String(value);

function ComparisonResult({ result, report }: { result: CategoricalComparison; report: AnalysisReport }) {
  if (result.status === "unavailable") return <p className="notice notice-info">{result.reason ?? "This comparison is unavailable."}</p>;
  const groups = result.group_categories ?? [], outcomes = result.outcome_categories ?? [];
  const counts = result.counts ?? [], percentages = result.row_percentages ?? [];
  return <div className="comparison-result" aria-live="polite">
    <div className="comparison-metrics"><div><span>Included rows</span><strong>{formatNumber(result.rows.included)}</strong></div><div><span>Excluded rows</span><strong>{formatNumber(result.rows.excluded)}</strong></div><div><span>p-value</span><strong>{formatNumber(result.test.p_value)}</strong></div><div><span>{result.association.method.name}</span><strong>{formatNumber(result.association.value)}</strong></div></div>
    {result.rows.excluded > 0 && <p className="muted comparison-exclusions">Excluded rows missing the group: {formatNumber(result.rows.exclusion_reasons.missing_group_value)}; missing the outcome: {formatNumber(result.rows.exclusion_reasons.missing_outcome_value)}. A row missing both is counted in both reasons.</p>}
    <div className="diagnostic-table-scroll" role="region" aria-label="Categorical comparison contingency table" tabIndex={0}><table className="diagnostic-table comparison-table"><caption>Counts, with the percentage of each group shown beneath. Percentages use that row's group total.</caption><thead><tr><th scope="col">{columnDisplayName(report, result.selection.group_column)}</th>{outcomes.map((outcome) => <th scope="col" key={label(outcome)}>{label(outcome)}</th>)}<th scope="col">Group total</th></tr></thead><tbody>{groups.map((group, row) => <tr key={label(group)}><th scope="row">{label(group)}</th>{outcomes.map((outcome, column) => <td key={label(outcome)}><strong>{formatNumber(counts[row]?.[column])}</strong><span>{formatPercentage(percentages[row]?.[column])} of group</span></td>)}<td><strong>{formatNumber(result.group_totals?.[row])}</strong></td></tr>)}<tr className="comparison-total-row"><th scope="row">Outcome total</th>{outcomes.map((outcome, column) => <td key={label(outcome)}><strong>{formatNumber(result.outcome_totals?.[column])}</strong></td>)}<td><strong>{formatNumber(result.rows.included)}</strong></td></tr></tbody></table></div>
    <section className="comparison-test" aria-labelledby={`comparison-test-${result.comparison_id}`}><h3 id={`comparison-test-${result.comparison_id}`}>{result.test.method.name}</h3><p>{result.test.method.evaluates}</p>{result.test.status === "ok" ? <p>Statistic: <strong>{formatNumber(result.test.statistic)}</strong> · Degrees of freedom: <strong>{formatNumber(result.test.degrees_of_freedom)}</strong> · p-value: <strong>{formatNumber(result.test.p_value)}</strong></p> : <p className="notice notice-info">{result.test.reason}</p>}{result.test.method.assumptions && <details><summary>Method assumptions</summary><ul>{result.test.method.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul></details>}</section>
    {result.warnings.map((warning) => <p className="notice notice-warning" key={warning}>{warning}</p>)}<p className="notice notice-info">{result.note}</p>
  </div>;
}

export function CategoricalComparisonPanel({ report, disabled = false }: { report: AnalysisReport; disabled?: boolean }) {
  const columns = (report.column_profiles ?? []).filter((profile) => profile.category === "categorical");
  const [groups, setGroups] = useState<string[]>(columns[0]?.name ? [columns[0].name] : []);
  const [outcomes, setOutcomes] = useState<string[]>(columns[1]?.name ? [columns[1].name] : []);
  const [results, setResults] = useState<CategoricalComparison[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const requestRef = useRef<AbortController | null>(null);
  useEffect(() => () => requestRef.current?.abort(), []);
  const clearPrevious = () => { setResults([]); setError(""); requestRef.current?.abort(); setLoading(false); };
  const toggleGroup = (value: string) => { setGroups((current) => current.includes(value) ? current.filter((name) => name !== value) : [...current, value]); clearPrevious(); };
  const toggleOutcome = (value: string) => { setOutcomes((current) => current.includes(value) ? current.filter((name) => name !== value) : [...current, value]); clearPrevious(); };
  const run = async () => {
    const pairs = groups.flatMap((group) => outcomes.filter((outcome) => outcome !== group).map((outcome) => ({ group, outcome })));
    if (pairs.length === 0) return;
    requestRef.current?.abort(); const controller = new AbortController(); requestRef.current = controller;
    setLoading(true); setError(""); setResults([]);
    const settled = await Promise.allSettled(pairs.map(({ group, outcome }) => compareCategoricalColumns(report.analysis_id, group, outcome, controller.signal)));
    if (controller.signal.aborted) return;
    const completed = settled.flatMap((item) => item.status === "fulfilled" ? [item.value] : []);
    const failed = settled.filter((item) => item.status === "rejected") as PromiseRejectedResult[];
    setResults(completed);
    if (failed.length) { const first = failed[0].reason; setError(`${failed.length} of ${settled.length} comparisons could not be completed. ${first instanceof ApiError ? first.message : "Please try again."}`); }
    if (requestRef.current === controller) setLoading(false);
  };
  const pairCount = groups.reduce((count, group) => count + outcomes.filter((outcome) => outcome !== group).length, 0);
  const picker = (side: "groups" | "outcomes") => {
    const selected = side === "groups" ? groups : outcomes;
    const unavailable = side === "groups" ? outcomes : groups;
    const toggle = side === "groups" ? toggleGroup : toggleOutcome;
    const selectedLabels = selected.map((name) => columnDisplayName(report, name));
    return <fieldset className="comparison-outcomes"><legend>{side === "groups" ? "Group columns" : "Outcome columns"}</legend><details className="multi-column-picker"><summary><span>{selectedLabels.length ? selectedLabels.join(", ") : "Select columns"}</span><small>{selected.length} selected</small></summary><div>{columns.map((column) => { const blocked = unavailable.includes(column.name); return <label className={blocked ? "picker-option-disabled" : undefined} key={column.name}><input type="checkbox" checked={selected.includes(column.name)} disabled={loading || blocked} onChange={() => toggle(column.name)} /><span>{columnDisplayName(report, column.name)}</span>{blocked && <em>Selected on other side</em>}</label>; })}</div></details><small>Select one or more categorical columns.</small></fieldset>;
  };
  return <section className="panel comparison-panel" aria-labelledby="comparison-title"><div><p className="eyebrow">RELATIONSHIPS</p><h2 id="comparison-title">Compare categorical columns</h2><p className="muted">Choose one or more columns on each side. Columns selected on one side are disabled on the other.</p></div>{columns.length < 2 ? <p className="notice notice-info">At least two categorical columns are needed for a comparison.</p> : <><div className="comparison-controls comparison-controls-symmetric">{picker("groups")}<span className="comparison-versus" aria-hidden="true">vs.</span>{picker("outcomes")}<button className="button button-primary" type="button" disabled={disabled || loading || pairCount === 0} onClick={() => void run()}>{loading ? `Running ${pairCount}…` : `Run ${pairCount || ""} comparison${pairCount === 1 ? "" : "s"}`}</button></div>{disabled && <p className="notice notice-info">Comparisons are disabled in the illustrative sample. Upload a dataset to run one.</p>}{error && <div className="notice notice-error" role="alert"><span>{error}</span><button className="button button-secondary" type="button" onClick={() => void run()}>Retry</button></div>}{results.map((result) => <section className="comparison-result-card" key={result.comparison_id}><h3>{columnDisplayName(report, result.selection.group_column)} × {columnDisplayName(report, result.selection.outcome_column)}</h3><ComparisonResult result={result} report={report} /></section>)}</>}</section>;
}
