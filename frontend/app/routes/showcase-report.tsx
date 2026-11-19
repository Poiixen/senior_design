import { Link, redirect } from "react-router";
import { getCurrentUser, getReport, requestJson, generateReportSuggestions, ApiError } from "~/lib/api";
import { EvidenceVisual } from "~/components/evidence-visual";
import { FindingCard } from "~/components/finding-card";
import type { Route } from "./+types/showcase-report";
import "./report.css";
import "./report-overview.css";
import "./showcase.css";

export async function clientLoader() {
  try {
    const user = await getCurrentUser();
    if (user.email !== "showcase@demo.invalid") return redirect("/showcase");
    const body = await requestJson("/api/reports", { signal: AbortSignal.timeout(20000) }) as { reports: { analysis_id: number }[] };
    const id = body.reports[0]?.analysis_id;
    if (!id) return redirect("/showcase");
    const report = await getReport(String(id), AbortSignal.timeout(20000));
    const suggestions = await generateReportSuggestions(id, AbortSignal.timeout(20000), { limit: 20 });
    return { report, suggestions };
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return redirect("/showcase");
    throw error;
  }
}

export function HydrateFallback() { return <main id="showcase-content" className="showcase" role="status">Opening the saved demo report…</main>; }
export function ErrorBoundary() { return <main id="showcase-content" className="showcase"><h1>We couldn’t load the demo</h1><p>Your connection may be slow or the demo may be restarting.</p><Link className="button" to="/showcase">Return and retry</Link></main>; }

export default function ShowcaseReport({ loaderData }: Route.ComponentProps) {
  const { report, suggestions } = loaderData;
  const comparisons = suggestions.suggestions.filter(s => s.finding_type === "group_difference" || s.finding_type === "categorical_association");
  const findings = suggestions.suggestions.filter(s => s.finding_type !== "group_difference" && s.finding_type !== "categorical_association");
  return <main id="showcase-content" className="showcase"><Link to="/showcase">← Showcase home / restart session</Link>
    <h1>A closer look at workshop attendance</h1><p>Explore {report.dataset.rows} made-up workshop records. Spot missing ratings, compare groups, and see what to check next.</p>
    <nav aria-label="Demo walkthrough"><a href="#overview">Explore findings</a><a href="#comparisons">Compare two columns</a><a href="#suggestions">Read suggestions</a></nav>
    <section id="overview"><h2>Explore findings</h2><p>This example is read-only. Nothing you explore changes the saved data.</p>
      <div className="showcase-counts"><p><strong>{report.dataset.rows}</strong> records</p><p><strong>{report.dataset.columns}</strong> columns</p><p><strong>{report.summary.duplicate_rows}</strong> repeated rows</p></div>
    </section>
    <section id="comparisons"><h2>Compare two columns</h2><p>Choose a comparison to see the groups side by side.</p>
      {comparisons.map(s => <details key={s.finding_id}><summary>{s.title}</summary><FindingCard finding={s} chart={false} />{s.visual && <EvidenceVisual spec={s.visual} compact />}</details>)}
      <Link to={`/reports/${report.analysis_id}?view=columns`}>Explore full report and saved comparisons</Link>
    </section>
    <section id="suggestions"><h2>Read suggestions</h2>{findings.slice(0, 3).map(s => <FindingCard key={s.finding_id} finding={s} />)}
      {findings.length > 3 && <details><summary>More findings ({findings.length - 3})</summary>{findings.slice(3).map(s => <FindingCard key={s.finding_id} finding={s} />)}</details>}
    </section>
    <p>Sessions expire after five idle minutes. <Link to="/showcase">Tap Try Demo again</Link> to return; the prepared report stays saved.</p>
  </main>;
}
