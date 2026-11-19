import type { ReportSuggestion } from "~/lib/api";
import type { ReactNode } from "react";
import { EvidenceTable, EvidenceVisual } from "./evidence-visual";

/** Show the takeaway first; retain methods and full precision one tap away. */
export function FindingCard({ finding: s, id, chart = true, condensed = false, evidenceLinks }: { finding: ReportSuggestion; id?: string; chart?: boolean; condensed?: boolean; evidenceLinks?: ReactNode }) {
  if (condensed) return <article className="suggestion-card suggestion-card-condensed" id={id}>
    <h3>{s.title}</h3>
    <p className="finding-takeaway">{s.plain_summary || s.explanation}</p>
    {s.plain_caution && <p className="finding-caution">{s.plain_caution}</p>}
    {!s.plain_summary && s.warnings?.map((warning, i) => <p className="finding-caution" key={i}>{warning}</p>)}
    {s.recommended_action && <p className="finding-next-step"><strong>Next step</strong><span>{s.recommended_action}</span></p>}
    <details className="finding-support">
      <summary>Explore evidence and next steps</summary>
      <div className="finding-support-content">
        {chart && s.visual && <EvidenceVisual spec={s.visual} compact />}
        {s.plain_summary && <p>{s.explanation}</p>}
        {s.evidence.length > 0 && <ul>{s.evidence.map((e, i) => <li key={i}>{e}</li>)}</ul>}
        {s.next_steps.length > 0 && <><h4>Further steps</h4><ul>{s.next_steps.map((step, i) => <li key={i}>{step}</li>)}</ul></>}
        {evidenceLinks}
        <details className="finding-statistics"><summary>Method and saved numbers</summary>
          {s.priority_reason && <p><strong>Why shown:</strong> {s.priority_reason}</p>}
          <p className="muted">{s.wording_source === "ai" ? "AI-assisted wording based on saved results." : "Guidance from saved results."}</p>
          {s.evidence_values && <EvidenceTable data={s.evidence_values} />}
        </details>
      </div>
    </details>
  </article>;
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
