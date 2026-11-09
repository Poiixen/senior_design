import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { ApiError, generateReportSuggestions, type SuggestionResponse } from "~/lib/api";
import { evidenceHref, type Comparison } from "~/lib/analysis";
import { EvidenceTable, EvidenceVisual } from "./evidence-visual";
import { ReportFollowup } from "./report-followup";

export function ReportSuggestions({ analysisId, disabled = false, comparisons = [], contextRevision = 0, comparisonsReady = true }: { analysisId: number; disabled?: boolean; comparisons?: Comparison[]; contextRevision?: number; comparisonsReady?: boolean }) {
  const [response, setResponse] = useState<SuggestionResponse | null>(null);
  const [error, setError] = useState(""), [loading, setLoading] = useState(false);
  const [selection, setSelection] = useState<number[] | null>(null), [generatedContext, setGeneratedContext] = useState("");
  const [retryMore, setRetryMore] = useState(false);
  const requestRef = useRef<AbortController | null>(null);
  const ids = selection ?? comparisons.map(c => c.comparison_id);
  const context = JSON.stringify([analysisId, contextRevision, ids, comparisons.map(c => [c.comparison_id, c.created_at])]);
  const stale = !!response && context !== generatedContext;
  useEffect(() => { requestRef.current?.abort(); setLoading(false); setError(""); }, [context]);
  useEffect(() => { setResponse(null); setSelection(null); setGeneratedContext(""); return () => requestRef.current?.abort(); }, [analysisId]);
  const generate = async (more = false) => {
    if (disabled || loading || !comparisonsReady || (more && stale)) return;
    requestRef.current?.abort(); const controller = new AbortController(); requestRef.current = controller;
    setLoading(true); setError(""); setRetryMore(more);
    try {
      const next = await generateReportSuggestions(analysisId, controller.signal, { comparison_ids: ids, offset: more ? response?.suggestions.length ?? 0 : 0, limit: more ? 20 : 5 });
      if (controller.signal.aborted || next.analysis_id !== analysisId) return;
      if (more && response?.evidence_fingerprint !== next.evidence_fingerprint) { setGeneratedContext(""); setError("Evidence changed while loading more findings. Regenerate suggestions."); return; }
      const page = next.suggestions.map(s => ({ ...s, wording_source: next.source }));
      setResponse({ ...next, suggestions: more && response ? [...response.suggestions, ...page] : page }); setGeneratedContext(context);
    } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : "Suggestions could not be generated."); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  };
  return <><section className="panel suggestions-panel" aria-labelledby="suggestions-title"><div className="suggestions-heading"><div><p className="eyebrow">EVIDENCE & NEXT STEPS</p><h2 id="suggestions-title">Worth Noting</h2><p className="muted">Ranked findings from this report. Priority reflects evidence, impact and reliability, not p-values alone.</p></div><button className="button button-primary" type="button" disabled={disabled || loading || !comparisonsReady} onClick={() => void generate()}>{loading ? "Generating…" : response ? "Regenerate suggestions" : "Generate suggestions"}</button></div>
    {!!comparisons.length && <details><summary>Comparison context ({ids.length} saved results)</summary><label><input type="checkbox" checked={selection === null} onChange={e => setSelection(e.target.checked ? null : [])} />Use all saved comparisons</label>{comparisons.map(c => <label className="finding-context" key={c.comparison_id}><input type="checkbox" checked={ids.includes(c.comparison_id)} onChange={e => setSelection(e.target.checked ? [...ids, c.comparison_id] : ids.filter(id => id !== c.comparison_id))} />#{c.comparison_id} {c.selection.group_column} · {c.test.method.name} · {c.regrouping ? "Regrouped" : "Original"}</label>)}</details>}
    {disabled && <p className="notice notice-info">Suggestions are unavailable for the illustrative sample. Upload a dataset to generate them.</p>}{!disabled && !comparisonsReady && <p className="notice notice-info">Load saved comparison context before generating suggestions. Use Retry saved context below if loading failed.</p>}
    {stale && <p className="notice notice-warning" role="status">Outdated findings: comparison context changed. Regenerate suggestions before using these findings for the updated context.</p>}
    {loading && <p role="status">Reviewing this report’s evidence…</p>}{error && <p className="notice notice-error" role="alert">{error} <button type="button" disabled={loading} onClick={() => void generate(retryMore && !stale)}>Retry</button></p>}
    {response && <div className="suggestions-results"><p><span className="badge badge-neutral">{new Set(response.suggestions.map(s => s.wording_source)).size > 1 ? "AI and fallback guidance" : response.source === "ai" ? "AI-generated" : "Fallback guidance"}</span> · {response.suggestions.length} of {response.total_findings ?? response.suggestions.length} findings</p>{response.suggestions.length === 0 && <p>No noteworthy findings were returned for this report.</p>}{response.suggestions.map((s, i) => <article className="suggestion-card" id={`finding-${s.finding_id ?? i}`} key={s.finding_id ?? i}><h3>{s.title}</h3><span className="badge badge-neutral">{s.wording_source === "ai" ? "AI-generated" : "Fallback guidance"}</span><p><strong>Why surfaced:</strong> {s.priority_reason ?? "Saved report evidence suggests reviewing this finding."}</p><p><strong>Affected columns:</strong> {s.affected_columns.join(", ") || "Dataset-wide"}</p>{s.warnings?.map((w, j) => <p className="notice notice-warning" key={j}>{w}</p>)}{s.exploratory && <p className="notice notice-warning">Exploratory finding across selected comparisons; this is not a confirmed discovery.</p>}<p>{s.explanation}</p>
      {s.visual ? <EvidenceVisual spec={s.visual} /> : <><p className="notice notice-info">This saved finding has no chart specification. Available evidence is shown below.</p><EvidenceTable data={s.evidence_values ?? { evidence: s.evidence }} /></>}
      <div className="suggestion-detail"><strong>Key evidence</strong><ul>{s.evidence.map((e, j) => <li key={j}>{e}</li>)}</ul></div>{s.finding_type === "duplicates" && <p>Duplicate rows are extra copies after keeping the first exact match across all source columns.</p>}
      {s.evidence_values && <details><summary>All supporting statistics and sample sizes</summary><EvidenceTable data={s.evidence_values} /></details>}<div className="suggestion-detail"><strong>Suggested next steps</strong><ul>{s.next_steps.map((step, j) => <li key={j}>{step}</li>)}</ul></div><div className="evidence-links">{s.evidence_refs?.length ? s.evidence_refs.map((ref, j) => <Link key={j} to={evidenceHref(ref)}>Inspect {ref.comparison_id != null ? `result #${ref.comparison_id}` : `${ref.result_type.replaceAll("_", " ")}${ref.column ? `: ${ref.column}` : ""}`} (report #{ref.analysis_id})</Link>) : <Link to="?view=columns">Inspect full report details</Link>}</div></article>)}{response.has_more && <button className="button button-secondary" type="button" disabled={loading || stale} onClick={() => void generate(true)}>View more findings</button>}</div>}
  </section><ReportFollowup key={analysisId} analysisId={analysisId} disabled={disabled} /></>;
}
