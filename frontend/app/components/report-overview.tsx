import { Link } from "react-router";
import { Icon } from "~/components/icon";
import { formatNumber, type AnalysisReport } from "~/lib/report";

export function ReportOverview({ report, preview = false }: { report: AnalysisReport; preview?: boolean }) {
  const { summary, dataset } = report;
  const label = (name: string) => report.column_display_names?.[name] || name;
  const other = Math.max(0, dataset.columns - summary.numeric_columns - summary.categorical_columns);
  const types = [
    { label: "Numeric", count: summary.numeric_columns, color: "#a794ff" },
    { label: "Categorical", count: summary.categorical_columns, color: "#83dfbb" },
    { label: "Other", count: other, color: "#ccd6db" },
  ];
  const missing = [...report.missing_values].filter(item => item.missing_count > 0).sort((a, b) => (b.missing_percentage ?? -1) - (a.missing_percentage ?? -1));
  const outliers = report.outliers.filter(item => item.outlier_count > 0);
  const findings = [
    ...missing.slice(0, 2).map(item => ({ icon: "alert" as const, tone: "coral", title: `Missing values in ${label(item.column_name)}`, detail: item.missing_percentage === null ? `${formatNumber(item.missing_count)} values are missing.` : `${item.missing_percentage.toLocaleString("en-US", { maximumFractionDigits: 1 })}% of rows are missing a value.`, view: "missing" })),
    ...(summary.duplicate_rows > 0 ? [{ icon: "duplicate" as const, tone: "coral", title: "Possible duplicate rows", detail: `${formatNumber(summary.duplicate_rows)} repeated ${summary.duplicate_rows === 1 ? "row" : "rows"} detected.`, view: "duplicates" }] : []),
    ...outliers.slice(0, 1).map(item => ({ icon: "chart" as const, tone: "violet", title: `Outlier values in ${label(item.column_name)}`, detail: `${formatNumber(item.outlier_count)} values fall outside the expected range.`, view: "outliers" })),
  ];
  let offset = 0;
  const profiles = [...(report.column_profiles ?? [])].sort((a, b) => (b.missing_percentage ?? -1) - (a.missing_percentage ?? -1)).slice(0, 5);
  return <div className={`analysis-overview ${preview ? "analysis-preview" : ""}`}>
    <dl className="analysis-stat-grid">
      {([
        ["Total rows", dataset.rows, "Rows in this dataset", "report", "violet"],
        ["Total columns", dataset.columns, "Columns analyzed", "chart", "blue"],
        ["Issues detected", summary.issues_detected, "Findings to review", "alert", "coral"],
        ["Duplicate rows", summary.duplicate_rows, "Repeated rows detected", "duplicate", "lime"],
      ] as const).map(([title, value, detail, icon, tone]) => <div className="panel analysis-stat" key={title}><span className={`analysis-icon analysis-${tone}`}><Icon name={icon} /></span><div><dt>{title}</dt><dd>{formatNumber(value)}</dd><p className="muted">{detail}</p></div></div>)}
    </dl>
    <div className="analysis-overview-grid">
      <section className="panel analysis-card"><h2>Column types</h2><p className="muted">{formatNumber(dataset.columns)} columns in this dataset</p><div className="analysis-types">
        <div className="analysis-donut"><svg viewBox="0 0 160 160" role="img" aria-label={types.map(type => `${type.count} ${type.label.toLowerCase()} columns`).join(", ")}><circle cx="80" cy="80" r="60" fill="none" stroke="#eef0ef" strokeWidth="24" />{types.map(type => {
          const fraction = dataset.columns > 0 ? type.count / dataset.columns : 0;
          const segment = <circle key={type.label} cx="80" cy="80" r="60" fill="none" stroke={type.color} strokeWidth="24" pathLength="100" strokeDasharray={`${fraction * 100} ${100 - fraction * 100}`} strokeDashoffset={-offset} transform="rotate(-90 80 80)" />;
          offset += fraction * 100;
          return segment;
        })}</svg><div><strong>{formatNumber(dataset.columns)}</strong><span>Columns</span></div></div>
        <dl className="analysis-type-legend">{types.map(type => <div key={type.label}><i style={{ background: type.color }} /><dd>{formatNumber(type.count)}</dd><dt>{type.label}</dt><span>{dataset.columns ? `${Math.round(type.count / dataset.columns * 100)}%` : "—"}</span></div>)}</dl>
      </div></section>
      <section className="panel analysis-card"><h2>Key findings</h2><p className="muted">What stands out in your data</p><div className="analysis-findings">{findings.length ? findings.map((finding, index) => <Link key={`${finding.view}-${index}`} to={preview ? `/example-report?view=${finding.view}` : `?view=${finding.view}`} preventScrollReset className="analysis-finding"><span className={`analysis-icon analysis-${finding.tone}`}><Icon name={finding.icon} /></span><div><h3>{finding.title}</h3><p className="muted">{finding.detail}</p></div><Icon name="arrow-right" /></Link>) : <div className="analysis-no-findings"><Icon name={report.status === "completed" ? "check" : "clock"} /><p>{report.status === "completed" ? "No missing-value, duplicate, or outlier findings were detected." : "Analysis is incomplete. Findings may not yet be available."}</p></div>}</div>{report.validation.warnings.length > 0 && <p className="analysis-structure-link"><a href={preview ? "/example-report#structure-notes" : "#structure-notes"}>{report.validation.warnings.length} structural {report.validation.warnings.length === 1 ? "warning" : "warnings"} to review <Icon name="arrow-right" /></a></p>}</section>
    </div>
    {!preview && <section className="panel analysis-card analysis-highlights"><div className="analysis-section-heading"><div><h2>Column highlights</h2><p className="muted">A closer look at each column</p></div><Link className="button button-secondary" to="?view=columns" preventScrollReset>View all columns<Icon name="arrow-right" /></Link></div>
      {profiles.length ? <div className="analysis-table-scroll" role="region" aria-label="Column highlights" tabIndex={0}><table className="analysis-highlight-table"><thead><tr><th scope="col">Column name</th><th scope="col">Type</th><th scope="col">Missing values</th><th scope="col">Unique values</th><th scope="col">Notes</th><th scope="col"><span className="report-sr-only">Explore</span></th></tr></thead><tbody>{profiles.map(profile => {
        const outlier = report.outliers.find(item => item.column_name === profile.name);
        const note = profile.missing_percentage === 100 ? "Entire column is missing." : profile.missing_count > 0 ? "Some values are missing." : outlier && outlier.outlier_count > 0 ? `${outlier.outlier_count} outlier values detected.` : "No missing values or outliers detected.";
        return <tr key={profile.name}><th scope="row">{label(profile.name)}</th><td><span className={`analysis-type-dot ${profile.category}`} />{profile.category === "numeric" ? "Numeric" : "Categorical"}</td><td><span className={`analysis-percentage ${profile.missing_percentage === null ? "unknown" : profile.missing_percentage >= 20 ? "high" : profile.missing_percentage > 0 ? "moderate" : "none"}`}>{profile.missing_percentage === null ? "Unavailable" : `${profile.missing_percentage.toLocaleString("en-US", { maximumFractionDigits: 1 })}%`}</span></td><td>{formatNumber(profile.unique_values)}</td><td>{note}</td><td><Link to="?view=columns" aria-label={`Explore ${label(profile.name)}`}><Icon name="arrow-right" /></Link></td></tr>;
      })}</tbody></table></div> : <p className="analysis-no-findings muted">Column highlights are unavailable for this older report. Open Columns to view the available details.</p>}
    </section>}
  </div>;
}
