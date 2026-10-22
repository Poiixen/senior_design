import { useEffect, useRef, useState } from "react";
import { ApiError, generateReportSuggestions, type SuggestionResponse } from "~/lib/api";

export function ReportSuggestions({ analysisId, disabled = false }: { analysisId: number; disabled?: boolean }) {
  const [response, setResponse] = useState<SuggestionResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const requestRef = useRef<AbortController | null>(null);
  const generationRef = useRef(0);

  useEffect(() => {
    generationRef.current += 1;
    requestRef.current?.abort();
    setResponse(null); setError(""); setLoading(false);
    return () => requestRef.current?.abort();
  }, [analysisId]);

  const generate = async () => {
    if (disabled || loading) return;
    requestRef.current?.abort();
    const controller = new AbortController();
    const generation = ++generationRef.current;
    requestRef.current = controller; setLoading(true); setError("");
    try {
      const next = await generateReportSuggestions(analysisId, controller.signal);
      if (generation === generationRef.current && next.analysis_id === analysisId) setResponse(next);
    } catch (reason) {
      if (generation === generationRef.current && !(reason instanceof Error && reason.name === "AbortError")) {
        setError(reason instanceof ApiError ? reason.message : "Suggestions could not be generated.");
      }
    } finally {
      if (generation === generationRef.current) setLoading(false);
    }
  };

  return (
    <section className="panel suggestions-panel" aria-labelledby="suggestions-title">
      <div className="suggestions-heading"><div><p className="eyebrow">NEXT STEPS</p><h2 id="suggestions-title">Dataset suggestions</h2><p className="muted">Generate evidence-based actions from this report’s findings.</p></div><button className="button button-primary" type="button" disabled={disabled || loading} onClick={() => void generate()}>{loading ? "Generating…" : response ? "Regenerate suggestions" : "Generate suggestions"}</button></div>
      {disabled && <p className="notice notice-info">Suggestions are unavailable for the illustrative sample. Upload a dataset to generate them.</p>}
      {loading && <p className="notice notice-progress" role="status" aria-live="polite">Reviewing this report’s evidence…</p>}
      {error && <div className="notice notice-error" role="alert"><span>{error}</span><button className="button button-secondary" type="button" onClick={() => void generate()}>Retry</button></div>}
      {response && <div className="suggestions-results" aria-live="polite"><p><span className={`badge ${response.source === "ai" ? "badge-success" : "badge-neutral"}`}>{response.source === "ai" ? "AI-generated" : "Fallback guidance"}</span></p>{response.suggestions.length === 0 ? <p className="notice notice-info">No suggestions were returned for this report.</p> : response.suggestions.map((suggestion, index) => <article className="suggestion-card" key={`${index}-${suggestion.title}`}><h3>{suggestion.title}</h3>{suggestion.affected_columns.length > 0 && <ul className="suggestion-columns" aria-label="Affected columns">{suggestion.affected_columns.map((column) => <li key={column}>{column}</li>)}</ul>}<p>{suggestion.explanation}</p><div className="suggestion-detail"><strong>Evidence</strong><ul>{suggestion.evidence.map((item) => <li key={item}>{item}</li>)}</ul></div><div className="suggestion-detail"><strong>Next steps</strong><ul>{suggestion.next_steps.map((item) => <li key={item}>{item}</li>)}</ul></div></article>)}</div>}
    </section>
  );
}
