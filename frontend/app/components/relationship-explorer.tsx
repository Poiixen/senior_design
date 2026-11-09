import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { createComparison, type Category, type Comparison, type Mapping, type NumericComparison } from "~/lib/analysis";
import { columnDisplayName, formatNumber, type AnalysisReport, type CategoricalColumnProfile } from "~/lib/report";
import { CategoricalComparisonPanel, ComparisonResult } from "./categorical-comparison";
import { Bars, BoxPlot, EvidenceTable, EvidenceVisual } from "./evidence-visual";

const methods = [
  ["auto", "Automatic: means for 2 groups; ranks for 3+"],
  ["welch_t_test", "Welch t-test: do two independent group means differ?"],
  ["welch_anova", "Welch ANOVA: do 3+ independent group means differ?"],
  ["kruskal_wallis", "Kruskal–Wallis: do ranks differ across 2+ groups?"],
];
const categoryKey = (c: Category) => `${typeof c}:${JSON.stringify(c)}`;

function RegroupEditor({ profile, mappings, onChange }: { profile: CategoricalColumnProfile; mappings: Mapping[]; onChange: (m: Mapping[]) => void }) {
  const [selected, setSelected] = useState<Category[]>([]), [name, setName] = useState("");
  const [error, setError] = useState("");
  const distribution = profile.distribution;
  if (!distribution) return <p className="notice notice-info">Category counts were not saved for {profile.name}. Upload the dataset again to configure regrouping.</p>;
  const assigned = new Set(mappings.flatMap(m => m.categories.map(categoryKey)));
  const add = () => {
    const label = name.trim();
    if (mappings.some(m => m.label === label) || distribution.categories.some(c => c.label === label && !selected.some(s => categoryKey(s) === categoryKey(c.label)))) { setError("This label already exists outside the selected categories. Choose a distinct label."); return; }
    onChange([...mappings, { label, categories: selected }]); setSelected([]); setName(""); setError("");
  };
  return <details className="regroup-editor"><summary>Category counts and regrouping: {profile.name}</summary><p>Counts use non-missing rows ({distribution.non_missing_rows}). Unmapped categories and missing values stay unchanged. Only this comparison uses the mapping.</p>{distribution.categories_truncated && <p className="notice notice-warning">{distribution.omitted_categories} categories ({distribution.omitted_count} rows) are omitted from this picker and will retain their original labels.</p>}
    <fieldset><legend>Select categories to combine</legend><div className="category-options">{distribution.categories.map(c => <label key={categoryKey(c.label)}><input type="checkbox" disabled={assigned.has(categoryKey(c.label))} checked={selected.some(s => categoryKey(s) === categoryKey(c.label))} onChange={e => setSelected(e.target.checked ? [...selected, c.label] : selected.filter(s => categoryKey(s) !== categoryKey(c.label)))} />{String(c.label)} <small>({typeof c.label}; n={c.count})</small></label>)}</div><label>Combined label<input value={name} onChange={e => setName(e.target.value)} /></label><button type="button" className="button button-secondary" disabled={!name.trim() || !selected.length} onClick={add}>Add mapping to preview</button>{error && <p role="alert">{error}</p>}</fieldset>
    {mappings.length > 0 && <div><h4>Mapping preview</h4>{mappings.map((m, i) => <p key={m.label}>{m.categories.map(c => JSON.stringify(c)).join(", ")} → <strong>{m.label}</strong> <button type="button" onClick={() => onChange(mappings.filter((_, j) => j !== i))}>Remove mapping</button></p>)}<p>Groups: {distribution.distinct_categories} → {distribution.distinct_categories - mappings.reduce((n, m) => n + m.categories.length - 1, 0)}. Changing the group count can change the automatic method; the saved result explains the actual method.</p></div>}
  </details>;
}

function NumericResult({ result }: { result: NumericComparison }) {
  const t = result.test, groups = result.groups ?? [];
  return <><h4>{t.method.name}</h4><p>{result.analysis_question?.text ?? t.method.evaluates}</p><p>{t.method.key === "kruskal_wallis" ? "Rank comparison, not a comparison of means." : "Mean comparison."}</p>{result.method_selection && <p>{result.method_selection.rule}</p>}
    <p>Rows: {result.rows.included} included / {result.rows.total} total; {result.rows.excluded} excluded.</p><EvidenceTable data={{ exclusion_reasons: result.rows.exclusion_reasons }} /><p className="muted">Exclusion reasons can overlap for the same row.</p>
    {result.status === "unavailable" && <p className="notice notice-warning">{result.reason}</p>}{t.status !== "ok" ? <p className="notice notice-warning">{t.reason}</p> : <p>{t.statistic_name ?? "Statistic"}: {formatNumber(t.statistic)} · Degrees of freedom: {formatNumber(t.degrees_of_freedom)}{t.degrees_of_freedom_within != null && `, denominator ${formatNumber(t.degrees_of_freedom_within)}`} · p-value: {t.p_value != null && t.p_value > 0 && t.p_value < .0001 ? t.p_value.toExponential(3) : formatNumber(t.p_value)}</p>}
    {t.mean_difference_ci && <p>{t.mean_difference_ci.level * 100}% confidence interval for the mean difference ({t.difference_order?.map(String).join(" minus ")}): [{formatNumber(t.mean_difference_ci.lower)}, {formatNumber(t.mean_difference_ci.upper)}]; difference {formatNumber(t.mean_difference)}. {t.mean_difference_ci.calculation}</p>}
    <p>{result.note}</p>{t.method.limitations?.map(l => <p key={l}>{l}</p>)}<details><summary>Method assumptions</summary><ul>{t.method.assumptions?.map(a => <li key={a}>{a}</li>)}</ul></details>
    {result.warnings.map(w => <p className="notice notice-warning" key={w}>{w}</p>)}
    {groups.length > 0 && <><BoxPlot groups={groups} label={result.selection.value_column} /><details><summary>Group means (descriptive)</summary><Bars rows={groups.filter(g => g.mean != null).map(g => ({ label: `${g.label} (n=${g.count})`, value: g.mean! }))} unit={result.selection.value_column} /><p>No group confidence intervals are supplied. Standard deviations below describe spread.</p></details><div className="diagnostic-table-scroll" tabIndex={0}><table className="diagnostic-table numeric-summary-table"><caption>Saved group summaries · units: {result.selection.value_column}</caption><thead><tr>{["Group", "n", "Mean", "Median", "SD", "Min", "Q1", "Q3", "Max", "Whisker low", "Whisker high", "Outliers"].map(h => <th key={h}>{h}</th>)}</tr></thead><tbody>{groups.map((g, i) => <tr key={i}><th scope="row">{String(g.label)}</th>{[g.count, g.mean, g.median, g.std_dev, g.min, g.q1, g.q3, g.max, g.whisker_low, g.whisker_high, g.outlier_count].map((n, j) => <td key={j}>{formatNumber(n)}</td>)}</tr>)}</tbody></table></div></>}
  </>;
}

export function SavedComparison({ result, report }: { result: Comparison; report: AnalysisReport }) {
  return <article id={`comparison-${result.comparison_id}`} className="comparison-result-card"><h3>Result #{result.comparison_id} · {result.regrouping ? "Regrouped" : "Original"} · {result.selection.group_column} × {result.comparison_type === "categorical_numeric" ? result.selection.value_column : result.selection.outcome_column}</h3><p className="muted">Saved {result.created_at}</p>
    {result.comparison_type === "categorical_numeric" ? <NumericResult result={result} /> : <><ComparisonResult result={result} report={report} />{result.status === "unavailable" && <><EvidenceTable data={{ rows: result.rows, test: result.test }} />{result.warnings.map(w => <p className="notice notice-warning" key={w}>{w}</p>)}</>}</>}
    {result.identifier_review?.map(r => <p className="notice notice-warning" key={r.column}>{r.column}: {r.reasons.join(" ")} {r.confirmed ? "Confirmed meaningful by user." : "Not confirmed by user."}</p>)}
    {result.regrouping && <section><h4>Exact saved category mapping</h4><EvidenceTable data={result.regrouping.mappings} /><p>{result.regrouping.method_change.explanation}</p><p>Group count: {result.regrouping.method_change.group_count_before} → {result.regrouping.method_change.group_count_after}</p><p>{result.regrouping.note}</p>{result.regrouping.original_comparison_id && <Link to={`?view=columns&comparison=${result.regrouping.original_comparison_id}#comparison-${result.regrouping.original_comparison_id}`}>Open original result #{result.regrouping.original_comparison_id}</Link>}{result.regrouping.columns.map(c => <EvidenceVisual key={c.column} spec={{ chart_type: "before_after_bar", title: `${c.column}: before / after`, data: { before: c.before, after: c.after }, units: "rows" }} />)}</section>}
  </article>;
}

export function RelationshipExplorer({ report, disabled, comparisons, onSaved, onContextChange, loading, error, onRetry }: { report: AnalysisReport; disabled: boolean; comparisons: Comparison[]; onSaved: () => void; onContextChange: () => void; loading: boolean; error: string; onRetry: () => void }) {
  const categorical = (report.column_profiles ?? []).filter((p): p is CategoricalColumnProfile => p.category === "categorical");
  const numeric = (report.column_profiles ?? []).filter(p => p.category === "numeric");
  const [kind, setKind] = useState("categorical_numeric"), [group, setGroup] = useState(categorical[0]?.name ?? ""), [value, setValue] = useState(numeric[0]?.name ?? ""), [method, setMethod] = useState("auto");
  const [mappings, setMappings] = useState<Record<string, Mapping[]>>({}), [confirmed, setConfirmed] = useState<string[]>([]);
  const [busy, setBusy] = useState(false), [failure, setFailure] = useState("");
  const request = useRef<AbortController | null>(null);
  const [params, setParams] = useSearchParams();
  const selected = comparisons.find(c => String(c.comparison_id) === params.get("comparison"));
  useEffect(() => () => request.current?.abort(), []);
  const change = () => { request.current?.abort(); setBusy(false); setFailure(""); onContextChange(); };
  const run = async () => {
    if (busy || disabled) return;
    const controller = new AbortController(); request.current = controller; setBusy(true); setFailure("");
    try {
      const result = await createComparison(report.analysis_id, { comparison_type: kind as "categorical_numeric" | "categorical_categorical", group_column: group, ...(kind === "categorical_numeric" ? { value_column: value, method } : { outcome_column: value }), category_mappings: mappings, confirm_columns: confirmed }, controller.signal);
      if (controller.signal.aborted) return;
      onSaved(); setParams({ view: "columns", comparison: String(result.comparison_id) }, { preventScrollReset: true });
    } catch (e) { if (!controller.signal.aborted) setFailure(e instanceof Error ? e.message : "Comparison unavailable."); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  };
  const selectedProfiles = categorical.filter(p => p.name === group || (kind === "categorical_categorical" && p.name === value));
  return <section className="panel relationship-explorer"><h2>Relationship explorer</h2><p>Compare independent groups. Choose meaningful categories and a measurement or categorical outcome.</p><fieldset disabled={disabled || busy}><legend>Comparison selection</legend><div className="relationship-controls">
    <label>Comparison type<select value={kind} onChange={e => { change(); setKind(e.target.value); setValue(e.target.value === "categorical_numeric" ? numeric[0]?.name ?? "" : categorical.find(p => p.name !== group)?.name ?? ""); setMappings({}); setConfirmed([]); }}><option value="categorical_numeric">Numerical measurement by category</option><option value="categorical_categorical">Categorical outcomes</option></select></label>
    <label>Grouping column<select value={group} onChange={e => { change(); setGroup(e.target.value); setMappings({}); setConfirmed([]); }}><option value="">Select a column</option>{categorical.map(p => <option key={p.name}>{p.name}</option>)}</select></label>
    <label>{kind === "categorical_numeric" ? "Numerical measurement" : "Outcome column"}<select value={value} onChange={e => { change(); setValue(e.target.value); setMappings({}); setConfirmed([]); }}><option value="">Select a column</option>{(kind === "categorical_numeric" ? numeric : categorical).filter(p => p.name !== group).map(p => <option key={p.name}>{p.name}</option>)}</select></label>
    {kind === "categorical_numeric" && <label>Analysis method<select value={method} onChange={e => { change(); setMethod(e.target.value); }}>{methods.map(([key, title]) => <option key={key} value={key}>{title}</option>)}</select></label>}
    </div>{selectedProfiles.map(p => <div key={p.name}>{p.identifier_review && <div className="notice notice-warning"><p>{p.identifier_review.reasons.join(" ")}</p><label><input type="checkbox" checked={confirmed.includes(p.name)} onChange={e => { change(); setConfirmed(e.target.checked ? [...confirmed, p.name] : confirmed.filter(n => n !== p.name)); }} />I reviewed {columnDisplayName(report, p.name)} and confirm it is meaningful for grouping.</label></div>}<RegroupEditor key={`${kind}-${group}-${value}-${p.name}`} profile={p} mappings={mappings[p.name] ?? []} onChange={m => { change(); setMappings(current => { const next = { ...current }; if (m.length) next[p.name] = m; else delete next[p.name]; return next; }); }} /></div>)}
    <button type="button" className="button button-primary" disabled={!group || !value || group === value} onClick={() => void run()}>{busy ? "Running comparison…" : "Run comparison"}</button></fieldset>
    {disabled && <p className="notice notice-info">Upload a dataset to run comparisons.</p>}{failure && <p className="notice notice-error" role="alert">{failure} <button type="button" onClick={() => void run()}>Retry comparison</button></p>}
    <h3>Saved results</h3>{loading && <p role="status">Loading saved comparisons…</p>}{error && <p role="alert">{error} <button type="button" onClick={onRetry}>Retry saved results</button></p>}<label>Open saved result<select value={selected?.comparison_id ?? ""} onChange={e => { change(); setParams({ view: "columns", ...(e.target.value ? { comparison: e.target.value } : {}) }, { preventScrollReset: true }); }}><option value="">Choose a result</option>{comparisons.map(c => <option key={c.comparison_id} value={c.comparison_id}>#{c.comparison_id} · {c.regrouping ? "Regrouped" : "Original"} · {c.selection.group_column} × {c.comparison_type === "categorical_numeric" ? c.selection.value_column : c.selection.outcome_column} · {c.test.method.name}</option>)}</select></label>{!loading && !comparisons.length && !error && <p>No saved comparisons yet.</p>}{params.has("comparison") && !selected && !loading && <p className="notice notice-info">The selected saved result is unavailable for this report.</p>}{selected && <SavedComparison result={selected} report={report} />}
    <details><summary>Compare multiple categorical columns</summary><CategoricalComparisonPanel report={report} disabled={disabled} onSaved={onSaved} /></details>
  </section>;
}
