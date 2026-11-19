import type { ReportSuggestion } from "~/lib/api";
import { EvidenceTable, EvidenceVisual } from "./evidence-visual";

/** Show the takeaway first; retain methods and full precision one tap away. */
export function FindingCard({ finding: s, id, chart = true }: { finding: ReportSuggestion; id?: string; chart?: boolean }) {
  return <article className="suggestion-card" id={id}>
    <h3>{s.title}</h3>
    {s.plain_caution && <p className="notice notice-warning">{s.plain_caution}</p>}
    {!s.plain_summary && s.warnings?.map((warning, i) => <p className="notice notice-warning" key={i}>{warning}</p>)}
    <p>{s.plain_summary || s.explanation}</p>
    {s.recommended_action && <p><strong>Try this:</strong> {s.recommended_action}</p>}
    {chart && (s.visual ? <details className="finding-chart"><summary>View chart: {s.visual.title}</summary><EvidenceVisual spec={s.visual} compact /></details> : <p>No chart is available. See the saved evidence in Statistical details.</p>)}
    <details className="finding-statistics"><summary>Statistical details</summary>
      {s.plain_summary && <p>{s.explanation}</p>}
      {s.wording_source && <p className="muted">{s.wording_source === "ai" ? "AI-assisted title and next steps; statistical explanations use saved results." : "Guidance from saved results."}</p>}
      {s.priority_reason && <p><strong>Why shown:</strong> {s.priority_reason}</p>}
      <ul>{s.evidence.map((e, i) => <li key={i}>{e}</li>)}</ul>
      {s.evidence_values && <details><summary>All saved numbers</summary><EvidenceTable data={s.evidence_values} /></details>}
      <h4>Further steps</h4><ul>{s.next_steps.map((step, i) => <li key={i}>{step}</li>)}</ul>
    </details>
  </article>;
}
