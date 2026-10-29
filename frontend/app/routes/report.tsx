import {
  isRouteErrorResponse,
  Link,
  redirect,
  useRevalidator,
  useSearchParams,
  type ShouldRevalidateFunctionArgs,
} from "react-router";
import { ColumnProfileTable } from "~/components/column-profile-table";
import { CategoricalComparisonPanel } from "~/components/categorical-comparison";
import { ReportSuggestions } from "~/components/report-suggestions";
import { ReportOverview } from "~/components/report-overview";
import { MissingValueTable, OutlierTable } from "~/components/diagnostic-tables";
import { DuplicateAnalysis } from "~/components/duplicate-analysis";
import { Icon } from "~/components/icon";
import { ApiError, getReport } from "~/lib/api";
import { formatNumber, type AnalysisReport } from "~/lib/report";
import type { Route } from "./+types/report";
import "./report.css";
import "./report-overview.css";

export function meta({ loaderData }: Route.MetaArgs) {
  return [
    { title: `${loaderData?.report.filename ?? "Analysis report"} · Team Science` },
    { name: "description", content: "Dataset analysis summary, column profiles, missing values, duplicates, and numeric outlier diagnostics." },
  ];
}

export async function clientLoader({ params, request }: Route.ClientLoaderArgs) {
  if (!params.analysisId || !/^[1-9]\d*$/.test(params.analysisId)) {
    throw new Response("Report not found", { status: 404 });
  }
  try { return { report: await getReport(params.analysisId, request.signal), isSample: false }; }
  catch (error) { if (error instanceof ApiError && error.status === 401) throw redirect(`/login?next=${encodeURIComponent(new URL(request.url).pathname)}`); throw error; }
}

export function shouldRevalidate({ currentUrl, nextUrl, defaultShouldRevalidate }: ShouldRevalidateFunctionArgs) {
  // The URL selects a presentation of the same complete report.
  if (currentUrl.pathname === nextUrl.pathname && currentUrl.search !== nextUrl.search) return false;
  return defaultShouldRevalidate;
}

const VIEWS = {
  columns: { tab: "Columns", title: "Column profiles" },
  missing: { tab: "Missing values", title: "Missing-value diagnostics" },
  duplicates: { tab: "Duplicates", title: "Duplicate analysis" },
  outliers: { tab: "Outliers", title: "Outlier diagnostics" },
} as const;
type DetailView = keyof typeof VIEWS;

function isDetailView(value: string | null): value is DetailView {
  return value !== null && Object.hasOwn(VIEWS, value);
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
  const { validation } = report;
  return <div className="report-summary-content">
    <ReportOverview report={report} />
    {(validation.warnings.length > 0 || validation.errors.length > 0) && <section id="structure-notes" className="notice notice-warning report-structure-notes" aria-labelledby="structure-title"><h2 id="structure-title">Structure notes</h2><p>These findings describe the dataset and may need review.</p><ul>{[...validation.warnings, ...validation.errors].map((warning, index) => <li key={`${index}-${warning}`}>{warning}</li>)}</ul></section>}
    <p className="analysis-method-note muted">The issue total counts columns with missing values, columns with outliers, structural warnings, and one finding when duplicate rows exist. Completed analyses can still contain findings to review.</p>
    {report.status !== "completed" && <p className="notice notice-warning" role="status">{report.status === "failed" ? "This analysis did not complete. Available results may be incomplete." : "Analysis is still running. Results may be incomplete until it finishes."}</p>}
  </div>;
}

function exportReport(report: AnalysisReport) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${report.filename.replace(/[^a-zA-Z0-9._-]/g, "_")}.analysis.json`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export default function Report({ loaderData }: Route.ComponentProps) {
  return <ReportContent report={loaderData.report} isSample={false} />;
}

export function ReportContent({ report, isSample }: { report: AnalysisReport; isSample: boolean }) {
  const [searchParams] = useSearchParams();
  const requestedView = searchParams.get("view");
  const view = isDetailView(requestedView) ? requestedView : "summary";
  const title = view === "summary" ? "Analysis report" : VIEWS[view].title;
  const statusText = report.status === "completed" ? "Completed" : report.status === "running" ? "In progress" : "Analysis failed";

  return (
    <div className="report-page">
      <header className="page-heading report-page-heading">
        <div>
          <p className="eyebrow">{view === "summary" ? "REPORT OVERVIEW" : "DETAILED DIAGNOSTICS"}</p>
          <div className="analysis-title-row"><h1>{report.filename}</h1><span className={`badge ${report.status === "completed" ? "badge-success" : report.status === "failed" ? "badge-error" : "badge-neutral"}`}>{statusText}</span></div>
          <p className="muted report-subtitle">{formatNumber(report.dataset.rows)} rows · {formatNumber(report.dataset.columns)} columns · {report.status === "completed" ? "Analyzed" : "Started"} <ReportTimestamp value={report.completed_at ?? report.started_at} /></p>
          {view !== "summary" && <h2 className="analysis-detail-title">{title}</h2>}
        </div>
        <button type="button" className="button analysis-export" onClick={() => exportReport(report)}>Export report<Icon name="arrow-down" /></button>
      </header>

      {isSample && <p className="notice notice-info">Sample report · Illustrative data for exploring the interface. Upload your own CSV to get actual analysis results.</p>}
      {!isSample && searchParams.get("uploaded") === "1" && <p className="notice notice-success" role="status">Your dataset was analyzed and the report was saved successfully.</p>}

      <nav className="panel report-tabs" aria-label="Report views">
        <Link to="." preventScrollReset aria-current={view === "summary" ? "page" : undefined}>Overview</Link>
        {(Object.keys(VIEWS) as DetailView[]).map((key) => (
          <Link key={key} to={`?view=${key}`} preventScrollReset aria-current={view === key ? "page" : undefined}>{VIEWS[key].tab}</Link>
        ))}
      </nav>

      {view === "summary" && <><Summary report={report} /><ReportSuggestions analysisId={report.analysis_id} disabled={isSample} /></>}
      {view === "columns" && <div className="report-columns-view"><ColumnProfileTable report={report} /><CategoricalComparisonPanel report={report} disabled={isSample} /></div>}
      {view === "missing" && <MissingValueTable report={report} />}
      {view === "duplicates" && <DuplicateAnalysis report={report} />}
      {view === "outliers" && <OutlierTable report={report} />}

      <footer className="report-footer">
        <Link className="button button-secondary" to={isSample ? "/register" : "/upload"}>{isSample ? "Create an account to analyze your data" : "Upload another dataset"} <span aria-hidden="true">→</span></Link>
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
        <Link className="button button-secondary" to="/upload">Upload a dataset</Link>
      </div>
    </section>
  );
}
