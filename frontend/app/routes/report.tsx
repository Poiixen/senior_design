import {
  isRouteErrorResponse,
  Link,
  useRevalidator,
  useSearchParams,
  type ShouldRevalidateFunctionArgs,
} from "react-router";
import { MissingValueTable, OutlierTable } from "~/components/diagnostic-tables";
import { Icon } from "~/components/icon";
import { getReport } from "~/lib/api";
import { formatNumber, type AnalysisReport } from "~/lib/report";
import { sampleReport } from "~/lib/sample-report";
import type { Route } from "./+types/report";
import "./report.css";

export function meta({ loaderData }: Route.MetaArgs) {
  return [
    { title: `${loaderData?.report.filename ?? "Analysis report"} · Team Science` },
    { name: "description", content: "Dataset analysis summary, missing values, and numeric outlier diagnostics." },
  ];
}

export async function loader({ params, request }: Route.LoaderArgs) {
  if (params.analysisId === "sample") return { report: sampleReport, isSample: true };
  if (!params.analysisId || !/^[1-9]\d*$/.test(params.analysisId)) {
    throw new Response("Report not found", { status: 404 });
  }
  return {
    report: await getReport(params.analysisId, request.signal, new URL(request.url).origin),
    isSample: false,
  };
}

export function shouldRevalidate({ currentUrl, nextUrl, defaultShouldRevalidate }: ShouldRevalidateFunctionArgs) {
  // The URL selects a presentation of the same complete report.
  if (currentUrl.pathname === nextUrl.pathname && currentUrl.search !== nextUrl.search) return false;
  return defaultShouldRevalidate;
}

export function HydrateFallback() {
  return (
    <section className="report-loading" aria-live="polite" aria-busy="true">
      <p className="eyebrow">DATASET VALIDATION</p>
      <h1>Loading analysis report</h1>
      <p className="notice notice-info">Retrieving your saved analysis…</p>
    </section>
  );
}

function ReportTimestamp({ value }: { value: string | null }) {
  if (!value) return <span>Unavailable</span>;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return <span>Unavailable</span>;
  return (
    <time dateTime={value}>
      {new Intl.DateTimeFormat("en-US", {
        month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short",
      }).format(date)}
    </time>
  );
}

function Summary({ report }: { report: AnalysisReport }) {
  const { summary, dataset, validation } = report;
  const completed = report.status === "completed";
  const hasIssues = summary.issues_detected > 0;
  return (
    <div className="report-summary-content">
      <dl className="panel report-metadata">
        <div><dt>File</dt><dd>{report.filename}</dd></div>
        <div><dt>Size</dt><dd>{formatNumber(dataset.rows)} rows × {formatNumber(dataset.columns)} columns</dd></div>
        <div><dt>{completed ? "Completed" : "Started"}</dt><dd><ReportTimestamp value={completed ? report.completed_at : report.started_at} /></dd></div>
      </dl>

      <dl className="report-metrics">
        <div className="panel report-metric report-metric-blue"><dt>Rows</dt><dd>{formatNumber(dataset.rows)}</dd><span className="metric-symbol"><Icon name="table" /></span></div>
        <div className="panel report-metric report-metric-purple"><dt>Columns</dt><dd>{formatNumber(dataset.columns)}</dd><span className="metric-symbol"><Icon name="columns" /></span></div>
        <div className="panel report-metric"><dt>Numeric / categorical</dt><dd>{formatNumber(summary.numeric_columns)} / {formatNumber(summary.categorical_columns)}</dd><span className="metric-symbol"><Icon name="chart" /></span></div>
        <div className="panel report-metric report-metric-amber"><dt>Duplicate rows</dt><dd>{formatNumber(summary.duplicate_rows)}</dd><span className="metric-symbol"><Icon name="duplicate" /></span></div>
      </dl>

      <section className="panel quality-overview" aria-labelledby="quality-title">
        <div className="quality-heading">
          <h2 id="quality-title">Quality overview</h2>
          <span className={`badge ${hasIssues ? "badge-warning" : completed ? "badge-success" : "badge-neutral"}`}>
            {hasIssues ? "Review suggested" : completed ? "No issues detected" : "Analysis incomplete"}
          </span>
        </div>
        <div className="report-issue-count">
          <strong>{formatNumber(summary.issues_detected)}</strong>
          <div>
            <span>Issues detected</span>
            <p className="muted">Counts affected missing-value columns, affected outlier columns, and structural warnings, plus one when duplicate rows are found.</p>
          </div>
        </div>
        <dl className="quality-rows">
          <div><dt>Missing values</dt><dd>{formatNumber(summary.missing_columns)} columns affected</dd><dd><Link to="?view=missing" preventScrollReset>Explore missing values <span aria-hidden="true">→</span></Link></dd></div>
          <div><dt>Outliers</dt><dd>{formatNumber(summary.outlier_columns)} numeric columns flagged</dd><dd><Link to="?view=outliers" preventScrollReset>Explore outliers <span aria-hidden="true">→</span></Link></dd></div>
          <div><dt>Duplicate rows</dt><dd>{formatNumber(summary.duplicate_rows)} repeated rows</dd><dd className="muted">{summary.duplicate_rows > 0 ? "Review repeated records" : "No duplicates detected"}</dd></div>
          <div><dt>Structure warnings</dt><dd>{formatNumber(validation.warnings.length)} warnings · non-blocking</dd><dd>{validation.warnings.length > 0 ? <a href="#structure-notes">View notes <span aria-hidden="true">→</span></a> : <span className="muted">No warnings</span>}</dd></div>
        </dl>
      </section>

      {(validation.warnings.length > 0 || validation.errors.length > 0) && (
        <section id="structure-notes" className="notice notice-warning report-structure-notes" aria-labelledby="structure-title">
          <h2 id="structure-title">Structure notes</h2>
          <p>These findings describe the dataset. They do not indicate an application failure.</p>
          <ul>{[...validation.warnings, ...validation.errors].map((warning, index) => <li key={`${index}-${warning}`}>{warning}</li>)}</ul>
        </section>
      )}
      <p className="notice notice-info">
        {completed
          ? hasIssues
            ? "Analysis completed successfully. The dataset still contains findings to review."
            : "Analysis completed successfully with no issues detected by the checks performed."
          : report.status === "failed"
            ? "This analysis did not complete. Any available measurements below may be incomplete."
            : "Analysis is still running. Results may be incomplete until it finishes."}
      </p>
    </div>
  );
}

export default function Report({ loaderData }: Route.ComponentProps) {
  const { report, isSample } = loaderData;
  const [searchParams] = useSearchParams();
  const requestedView = searchParams.get("view");
  const view = requestedView === "missing" || requestedView === "outliers" ? requestedView : "summary";
  const title = view === "missing" ? "Missing-value diagnostics" : view === "outliers" ? "Outlier diagnostics" : "Analysis report";
  const statusText = report.status === "completed" ? "Completed" : report.status === "running" ? "In progress" : "Analysis failed";

  return (
    <div className="report-page">
      <header className="page-heading report-page-heading">
        <div>
          <p className="eyebrow">{view === "summary" ? "REPORT OVERVIEW" : "DETAILED DIAGNOSTICS"}</p>
          <h1>{title}</h1>
          <p className="muted report-subtitle"><strong>{report.filename}</strong><span aria-hidden="true"> / </span>{view === "summary" ? "Understand your dataset at a glance." : "Review individual fields and understand the findings."}</p>
        </div>
        <span className={`badge ${report.status === "completed" ? "badge-success" : report.status === "failed" ? "badge-error" : "badge-neutral"}`}>{statusText}</span>
      </header>

      {isSample && <p className="notice notice-info">Sample report · Illustrative data for exploring the interface. Upload your own CSV to get actual analysis results.</p>}
      {!isSample && searchParams.get("uploaded") === "1" && <p className="notice notice-success" role="status">Your dataset was analyzed and the report was saved successfully.</p>}

      <nav className="panel report-tabs" aria-label="Report views">
        <Link to="." preventScrollReset aria-current={view === "summary" ? "page" : undefined}>Overview</Link>
        <Link to="?view=missing" preventScrollReset aria-current={view === "missing" ? "page" : undefined}>Missing values</Link>
        <Link to="?view=outliers" preventScrollReset aria-current={view === "outliers" ? "page" : undefined}>Outliers</Link>
      </nav>

      {view === "summary" ? <Summary report={report} /> : view === "missing" ? <MissingValueTable report={report} /> : <OutlierTable report={report} />}

      <footer className="report-footer">
        <Link className="button button-secondary" to="/">Upload another dataset <span aria-hidden="true">→</span></Link>
        <span className="muted">{isSample ? "Sample analysis" : `Analysis #${report.analysis_id}`}</span>
      </footer>
    </div>
  );
}

export function ErrorBoundary({ error }: Route.ErrorBoundaryProps) {
  const revalidator = useRevalidator();
  const status = isRouteErrorResponse(error)
    ? error.status
    : error instanceof Error && "status" in error ? error.status : undefined;
  const notFound = status === 404;
  const details = notFound
    ? "This analysis could not be found. Check the report address or upload a dataset to create a new report."
    : error instanceof Error ? error.message : "The report could not be retrieved. Please try again.";
  return (
    <section className="report-error">
      <p className="eyebrow">ANALYSIS REPORT</p>
      <h1>{notFound ? "Report not found" : "Unable to load report"}</h1>
      <p className="notice notice-error" role="alert">{details}</p>
      <div className="report-error-actions">
        <button className="button button-primary" type="button" disabled={revalidator.state === "loading"} onClick={() => void revalidator.revalidate()}>
          {revalidator.state === "loading" ? "Retrying…" : "Try again"}
        </button>
        <Link className="button button-secondary" to="/">Upload a dataset</Link>
      </div>
    </section>
  );
}
