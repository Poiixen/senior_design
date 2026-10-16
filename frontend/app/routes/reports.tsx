import { Link, redirect } from "react-router";
import type { Route } from "./+types/reports";
import { ApiError, getReports } from "~/lib/api";
import { formatNumber } from "~/lib/report";
import { Icon } from "~/components/icon";

export function meta() {
  return [
    { title: "Saved reports | Team Science" },
    { name: "description", content: "Review saved dataset analysis reports." },
  ];
}

export async function clientLoader({ request }: Route.ClientLoaderArgs) {
  try { return { reports: await getReports(request.signal) }; }
  catch (error) { if (error instanceof ApiError && error.status === 401) throw redirect("/login?next=/reports"); throw error; }
}

export function HydrateFallback() { return <section className="reports-empty"><p>Loading saved reports…</p></section>; }

function ReportDate({ value }: { value: string | null }) {
  if (!value) return <span>Not completed</span>;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return <span>Date unavailable</span>;
  return (
    <time dateTime={value}>
      {new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
      }).format(date)}
    </time>
  );
}

export default function Reports({ loaderData }: Route.ComponentProps) {
  const { reports } = loaderData;

  return <div className="reports-page">
    <header className="page-heading reports-heading">
      <div>
        <p className="eyebrow">REPORT HISTORY</p>
        <h1>Saved reports</h1>
        <p className="muted">Open results from datasets analyzed in this workspace.</p>
      </div>
      <Link className="button button-primary" to="/"><Icon name="upload" />Upload dataset</Link>
    </header>

    {reports.length === 0 ? (
      <section className="panel reports-empty">
        <Icon name="report" />
        <h2>No saved reports yet</h2>
        <p className="muted">Analyze a CSV dataset and its report will appear here.</p>
        <Link className="button button-primary" to="/">Upload your first dataset</Link>
      </section>
    ) : (
      <div className="report-list" aria-label="Saved analysis reports">
        {reports.map((report) => (
          <article className="panel report-list-item" key={report.analysis_id}>
            <div className="report-list-main">
              <span className="report-list-icon"><Icon name="report" /></span>
              <div>
                <h2><Link to={`/reports/${report.analysis_id}`}>{report.filename}</Link></h2>
                <p className="muted">Analysis #{report.analysis_id} / <ReportDate value={report.completed_at ?? report.started_at} /></p>
              </div>
            </div>
            <dl className="report-list-metrics">
              <div><dt>Rows</dt><dd>{formatNumber(report.dataset.rows)}</dd></div>
              <div><dt>Columns</dt><dd>{formatNumber(report.dataset.columns)}</dd></div>
              <div><dt>Issues</dt><dd>{formatNumber(report.summary.issues_detected)}</dd></div>
            </dl>
            <span className={`badge ${report.status === "completed" ? "badge-success" : report.status === "failed" ? "badge-error" : "badge-neutral"}`}>
              {report.status === "completed" ? "Completed" : report.status === "failed" ? "Failed" : "In progress"}
            </span>
            <Link className="button button-secondary" to={`/reports/${report.analysis_id}`}>View report</Link>
          </article>
        ))}
      </div>
    )}

    <p className="privacy-note reports-privacy"><Icon name="file" />Reports contain dataset metadata and diagnostic findings only. Raw CSV rows are not saved.</p>
  </div>;
}

export function ErrorBoundary() {
  return <section className="panel reports-empty">
    <Icon name="alert" />
    <h1>Unable to load saved reports</h1>
    <p className="muted">Check that the analysis service is running, then refresh this page.</p>
    <Link className="button button-secondary" to="/">Return to upload</Link>
  </section>;
}
