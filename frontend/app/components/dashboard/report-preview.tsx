import { Link } from "react-router";
import { Icon } from "~/components/icon";
import type { ReportSummary } from "~/lib/api";
import { knownCount, reportDate, validDate } from "~/lib/dashboard";

export function ReportDate({ value, compact = false }: { value: string | null; compact?: boolean }) {
  const date = validDate(value);
  return date ? <time dateTime={date}>{new Intl.DateTimeFormat("en-US", {
    month: "short", day: "numeric", year: "numeric", ...(!compact ? { hour: "numeric" as const, minute: "2-digit" as const } : {}),
  }).format(new Date(date))}</time> : <>Date unavailable</>;
}

export function ReportStatus({ status }: { status: ReportSummary["status"] }) {
  const label = status === "completed" ? "Completed" : status === "failed" ? "Failed" : status === "running" ? "In progress" : "Status unavailable";
  return <span className={`badge ${status === "completed" ? "badge-success" : status === "failed" ? "badge-error" : "badge-neutral"}`}>{label}</span>;
}

export function ReportCounts({ report }: { report: ReportSummary }) {
  return <dl className="dashboard-report-counts">{([
    ["Rows", report.dataset?.rows], ["Columns", report.dataset?.columns], ["Issues detected", report.summary?.issues_detected],
  ] as const).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{knownCount(value)?.toLocaleString("en-US") ?? "Unavailable"}</dd></div>)}</dl>;
}

export function ReportPreview({ report }: { report: ReportSummary }) {
  return <Link className="dashboard-report" to={`/reports/${report.analysis_id}`}>
    <span className="dashboard-icon tone-purple"><Icon name="file" /></span>
    <div className="dashboard-report-info"><h3>{report.filename || "Untitled dataset"}</h3><p className="muted">{validDate(report.completed_at) ? "Analyzed" : "Started"} · <ReportDate value={reportDate(report)} /></p><ReportCounts report={report} /></div>
    <ReportStatus status={report.status} /><Icon name="arrow-right" className="dashboard-report-arrow" />
  </Link>;
}
