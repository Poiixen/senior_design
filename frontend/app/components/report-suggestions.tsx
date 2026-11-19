import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { ApiError, generateReportSuggestions, type SuggestionResponse } from "~/lib/api";
import { evidenceHref, type Comparison } from "~/lib/analysis";
import { FindingCard } from "./finding-card";
import { ReportFollowup } from "./report-followup";

export function ReportSuggestions({ analysisId, disabled = false, comparisons = [], contextRevision = 0, comparisonsReady = true }: { analysisId: number; disabled?: boolean; comparisons?: Comparison[]; contextRevision?: number; comparisonsReady?: boolean }) {
  const [response, setResponse] = useState<SuggestionResponse | null>(null);
  const [error, setError] = useState(""), [loading, setLoading] = useState(false);
  const [selection, setSelection] = useState<number[] | null>(null), [generatedContext, setGeneratedContext] = useState("");
  const [followupOpened, setFollowupOpened] = useState(false);
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
      const next = await generateReportSuggestions(analysisId, controller.signal, { comparison_ids: ids, offset: more ? response?.suggestions.length ?? 0 : 0, limit: 5 });
      if (controller.signal.aborted || next.analysis_id !== analysisId) return;
      if (more && response?.evidence_fingerprint !== next.evidence_fingerprint) { setGeneratedContext(""); setError("Evidence changed while loading more findings. Regenerate suggestions."); return; }
      const page = next.suggestions.map(s => ({ ...s, wording_source: next.source }));
      setResponse({ ...next, suggestions: more && response ? [...response.suggestions, ...page] : page }); setGeneratedContext(context);
    } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : "Suggestions could not be generated."); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  };

  return <>
    <section className="panel suggestions-panel" aria-labelledby="suggestions-title" aria-busy={loading}>
      <div className="suggestions-heading">
        <div><h2 id="suggestions-title">Suggested next steps</h2><p className="muted">A short list of findings to help you decide what to explore next.</p></div>
        <button className={response ? "button button-secondary" : "button button-primary"} type="button" disabled={disabled || loading || !comparisonsReady} onClick={() => void generate()}>{loading && !retryMore ? "Generating..." : response ? "Refresh suggestions" : "Generate suggestions"}</button>
      </div>
      {!!comparisons.length && <details className="suggestions-context"><summary>Included comparisons ({ids.length} selected)</summary><div><label><input type="checkbox" checked={selection === null} onChange={e => setSelection(e.target.checked ? null : [])} /> Use all saved comparisons</label>{comparisons.map(c => <label className="finding-context" key={c.comparison_id}><input type="checkbox" checked={ids.includes(c.comparison_id)} onChange={e => setSelection(e.target.checked ? [...ids, c.comparison_id] : ids.filter(id => id !== c.comparison_id))} />#{c.comparison_id} {c.selection.group_column} ? {c.test.method.name} ? {c.regrouping ? "Regrouped" : "Original"}</label>)}</div></details>}
      {disabled && <p className="notice notice-info">Upload a dataset to generate suggestions for your own report.</p>}
      {!disabled && !comparisonsReady && <p className="notice notice-info">Waiting for saved comparisons. If loading failed, use Retry saved context below.</p>}
      {stale && <p className="notice notice-warning" role="status">Your comparison context changed. Refresh suggestions to use the latest results.</p>}
      {loading && <p role="status">{retryMore ? "Loading more findings..." : "Reviewing your report..."}</p>}
      {error && <p className="notice notice-error" role="alert">{error} <button type="button" disabled={loading} onClick={() => void generate(retryMore && !stale)}>Retry</button></p>}
      {response && <div className="suggestions-results">
        <p className="suggestions-count" role="status">{response.suggestions.length} of {response.total_findings ?? response.suggestions.length} findings</p>
        {response.suggestions.length === 0 && <p>No noteworthy findings were returned for this report.</p>}
        {response.suggestions.map((s, i) => <FindingCard key={s.finding_id ?? i} finding={s} id={"finding-" + (s.finding_id ?? i)} condensed evidenceLinks={
          <div className="evidence-links">{s.evidence_refs?.length ? s.evidence_refs.map((ref, j) => <Link key={j} to={evidenceHref(ref)}>Open {ref.comparison_id != null ? "comparison #" + ref.comparison_id : ref.result_type.replaceAll("_", " ") + (ref.column ? ": " + ref.column : "")}</Link>) : <Link to="?view=columns">Open report details</Link>}</div>
        } />)}
        {response.has_more && <button className="button button-secondary suggestions-more" type="button" disabled={loading || stale} onClick={() => void generate(true)}>{loading && retryMore ? "Loading..." : "Show more findings"}</button>}
      </div>}
    </section>
    <details className="panel suggestions-followup" onToggle={event => { if (event.currentTarget.open) setFollowupOpened(true); }}>
      <summary><span>Have a follow-up question?</span><span className="muted">Open report chat</span></summary>
      {followupOpened && <ReportFollowup key={analysisId} analysisId={analysisId} disabled={disabled} showDuplicatePreview={false} />}
    </details>
  </>;
}
