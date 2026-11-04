import { Link, redirect, useRevalidator } from "react-router";
import type { Route } from "./+types/dashboard";
import { Icon } from "~/components/icon";
import { MetricCard } from "~/components/dashboard/metric-card";
import { ReportCounts, ReportDate, ReportPreview, ReportStatus } from "~/components/dashboard/report-preview";
import { ApiError, getCurrentUser, getReports } from "~/lib/api";
import { dashboardOverview, reportDate } from "~/lib/dashboard";
import "./home.css";

export function meta() {
  return [{ title: "Workspace overview | Team Science" }, { name: "description", content: "Your datasets, saved analyses, and next steps in one workspace." }];
}

export async function clientLoader({ request }: Route.ClientLoaderArgs) {
  try {
    await getCurrentUser();
    return { reports: await getReports(request.signal) };
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) throw redirect("/login?next=/dashboard");
    throw error;
  }
}

export function HydrateFallback() {
  return <div className="dashboard dashboard-loading" role="status" aria-busy="true">
    <p className="eyebrow">YOUR WORKSPACE</p><h1>Loading your overview</h1><p className="muted">Retrieving your saved analyses…</p>
    <div className="dashboard-metrics" aria-hidden="true">{[0, 1, 2, 3].map(key => <div className="dashboard-skeleton" key={key} />)}</div>
  </div>;
}

export default function Dashboard({ loaderData }: Route.ComponentProps) {
  // GET /api/reports currently returns every saved report for this user, without pagination.
  // Calculate workspace totals before limiting the recent-report presentation.
  const overview = dashboardOverview(loaderData.reports);
  const { latest } = overview;
  return <div className="dashboard">
    <section className="dashboard-hero" aria-labelledby="welcome-heading">
      <div className="dashboard-welcome"><p className="eyebrow">WELCOME BACK · YOUR WORKSPACE</p><h1 id="welcome-heading">Good data.<br /><span>Better questions.</span></h1><p className="dashboard-intro">Upload data, check for issues, and explore patterns — all in one place.</p><div className="dashboard-buttons"><Link to="/upload" className="button button-primary"><Icon name="upload" />Analyze Dataset<Icon name="arrow-right" /></Link><Link to="/reports" className="button button-secondary">View Reports</Link></div><p className="dashboard-formats"><Icon name="check" />CSV, TSV, Excel & JSON supported</p></div>
      <aside className="dashboard-spotlight" aria-label={latest ? "Most recent saved report" : "Start your first analysis"}>
        <div className="dashboard-spotlight-top"><span className="dashboard-icon tone-purple"><Icon name={latest ? "report" : "chart"} /></span><p className="eyebrow">{latest ? "PICK UP WHERE YOU LEFT OFF" : "FROM DATA TO UNDERSTANDING"}</p></div>
        {latest ? <><h2>{latest.filename || "Untitled dataset"}</h2><p className="muted"><ReportDate value={reportDate(latest)} /></p><ReportStatus status={latest.status} /><ReportCounts report={latest} /><Link to={`/reports/${latest.analysis_id}`} className="dashboard-text-link">Reopen latest report<Icon name="arrow-right" /></Link></> : <><h2>Your next insight starts here.</h2><p className="muted">Bring a dataset. Get a clear view of its columns, missing values, duplicates, and outliers.</p><div className="dashboard-start-steps"><span><Icon name="upload" />Upload</span><Icon name="arrow-right" /><span><Icon name="chart" />Analyze</span><Icon name="arrow-right" /><span><Icon name="report" />Explore</span></div><Link to="/upload" className="dashboard-text-link">Start your first analysis<Icon name="arrow-right" /></Link></>}
      </aside>
    </section>

    <section aria-labelledby="overview-heading"><div className="dashboard-section-heading"><h2 id="overview-heading">Workspace at a glance</h2><span className="muted">Your saved analyses</span></div><div className="dashboard-metrics">
      <MetricCard label="Saved reports" value={overview.total.toLocaleString("en-US")} detail="Reports in your workspace" icon="report" />
      <MetricCard label="Completed analyses" value={overview.completed?.toLocaleString("en-US") ?? "Unavailable"} detail="Successfully finished analyses" icon="check" tone="green" />
      <MetricCard label="Reports with issues" value={overview.issuesUnavailable ? "Unavailable" : overview.withIssues.toLocaleString("en-US")} detail={overview.issuesUnavailable ? `${overview.withIssues} confirmed; ${overview.issuesUnavailable} missing issue counts` : "At least one finding to review"} icon="alert" tone="amber" />
      <MetricCard label="Most recent analysis" value={overview.latestAnalysisDate ? <ReportDate value={overview.latestAnalysisDate} compact /> : "Not available"} detail="Latest recorded completion date" icon="clock" tone="blue" />
    </div></section>

    <div className="dashboard-lower"><section className="dashboard-panel" aria-labelledby="recent-heading"><div className="dashboard-section-heading"><div><h2 id="recent-heading">Recent reports</h2><p className="muted">Your latest datasets, ready to revisit.</p></div><Link className="dashboard-text-link" to="/reports">View All Reports<Icon name="arrow-right" /></Link></div>
      {overview.total ? <div className="dashboard-report-list">{overview.recent.map(report => <ReportPreview key={report.analysis_id} report={report} />)}</div> : <div className="dashboard-empty"><span className="dashboard-icon tone-purple"><Icon name="report" /></span><h3>A fresh workspace. A clear start.</h3><p className="muted">No saved reports yet. Analyze your first dataset to see your results here.</p><Link to="/upload" className="button button-primary">Analyze your first dataset<Icon name="arrow-right" /></Link></div>}
    </section>
    <aside className="dashboard-panel dashboard-actions" aria-labelledby="actions-heading"><h2 id="actions-heading">Make your next move</h2><p className="muted">Everything you need to keep exploring.</p><Link to="/upload" className="dashboard-action"><span className="dashboard-icon tone-purple"><Icon name="upload" /></span><div><h3>Analyze a dataset</h3><p className="muted">Find quality issues and patterns.</p></div><Icon name="arrow-right" /></Link><Link to="/reports" className="dashboard-action"><span className="dashboard-icon tone-green"><Icon name="report" /></span><div><h3>Browse saved reports</h3><p className="muted">Return to your previous analyses.</p></div><Icon name="arrow-right" /></Link>{latest && <Link to={`/reports/${latest.analysis_id}`} className="dashboard-action"><span className="dashboard-icon tone-blue"><Icon name="clock" /></span><div><h3>Reopen latest report</h3><p className="muted dashboard-action-filename">{latest.filename || "Untitled dataset"}</p></div><Icon name="arrow-right" /></Link>}
      {latest?.status === "completed" && <div className="dashboard-explore"><p className="eyebrow">EXPLORE YOUR LATEST DATASET</p><Link to={`/reports/${latest.analysis_id}?view=columns`}>Column profiles<Icon name="arrow-right" /></Link><Link to={`/reports/${latest.analysis_id}?view=missing`}>Missing values<Icon name="arrow-right" /></Link><Link to={`/reports/${latest.analysis_id}?view=outliers`}>Numeric outliers<Icon name="arrow-right" /></Link></div>}
    </aside></div>
    <p className="dashboard-footer muted"><Icon name="file" />Your overview reflects saved report summaries. Open a report for detailed findings.</p>
  </div>;
}

export function ErrorBoundary() {
  const revalidator = useRevalidator();
  const busy = revalidator.state !== "idle";
  return <section className="dashboard dashboard-panel dashboard-empty" role="alert"><span className="dashboard-icon tone-amber"><Icon name="alert" /></span><h1>Unable to load your workspace</h1><p className="muted">We couldn’t retrieve your dashboard. Check your connection and try again.</p><div className="dashboard-buttons"><button className="button button-primary" type="button" disabled={busy} onClick={() => void revalidator.revalidate()}>{busy ? "Retrying…" : "Try again"}</button><Link to="/upload" className="button button-secondary">Analyze a dataset</Link></div></section>;
}
