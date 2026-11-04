import type { ReportSummary } from "./api";

export function validDate(value: string | null | undefined): string | null {
  return value && Number.isFinite(Date.parse(value)) ? value : null;
}

export function reportDate(report: ReportSummary): string | null {
  return validDate(report.completed_at) ?? validDate(report.started_at);
}

export function knownCount(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
}

export function dashboardOverview(reports: ReportSummary[]) {
  const recent = [...reports].sort((a, b) =>
    (Date.parse(reportDate(b) ?? "") || 0) - (Date.parse(reportDate(a) ?? "") || 0) || b.analysis_id - a.analysis_id);
  const completed = reports.filter(report => report.status === "completed");
  const datedAnalyses = completed.map(report => validDate(report.completed_at)).filter((date): date is string => date !== null);
  const issuesUnavailable = reports.filter(report => knownCount(report.summary?.issues_detected) === null).length;
  return {
    recent: recent.slice(0, 5),
    latest: recent[0] ?? null,
    total: reports.length,
    completed: reports.every(report => ["completed", "failed", "running"].includes(report.status)) ? completed.length : null,
    withIssues: reports.filter(report => (knownCount(report.summary?.issues_detected) ?? 0) > 0).length,
    issuesUnavailable,
    latestAnalysisDate: datedAnalyses.sort((a, b) => Date.parse(b) - Date.parse(a))[0] ?? null,
  };
}
