import { Link } from "react-router";
import { Icon } from "~/components/icon";
import { ReportOverview } from "~/components/report-overview";
import { sampleReport } from "~/lib/sample-report";
import "./report-overview.css";
import "./landing.css";

export function meta() {
  return [{ title: "Team Science | Turn data into better questions" }, { name: "description", content: "Upload datasets, review data quality, explore columns, and compare groups in one clear workspace." }];
}

const features = [
  { title: "Find missing data", text: "Quickly spot missing values, duplicates, and other quality issues that can affect your analysis.", icon: "alert", tone: "coral", to: "/example-report?view=missing" },
  { title: "Explore columns", text: "Understand your data with clear summaries, column types, and helpful visualizations.", icon: "report", tone: "violet", to: "/example-report?view=columns" },
  { title: "Compare groups", text: "Review relationships across categorical columns with the comparison tools in your report.", icon: "users", tone: "lime", to: "/documentation" },
  { title: "Generate insights", text: "Turn report findings into evidence-based suggestions and practical next steps.", icon: "bulb", tone: "blue", to: "/register" },
] as const;

export default function Home() {
  return <div className="landing-page">
    <header className="landing-nav"><Link className="landing-brand" to="/" aria-label="Team Science home"><span>TS</span>Team Science</Link><nav aria-label="Main navigation"><a href="#features">Product</a><a href="#workflow">How it works</a><Link to="/documentation">Resources</Link></nav><div className="landing-account"><Link to="/login">Sign in</Link><Link className="button landing-dark-button" to="/register">Get started<Icon name="arrow-right" /></Link></div></header>
    <main id="main-content">
      <section className="landing-hero" aria-labelledby="landing-title"><div className="landing-hero-copy"><p className="eyebrow">DATA QUALITY FOR BRIGHTER QUESTIONS</p><h1 id="landing-title">Turn messy datasets<br />into clear decisions.</h1><p className="landing-lead">Upload data, surface quality issues, explore patterns, and move from raw files to better questions.</p><div className="landing-buttons"><Link className="button button-primary" to="/register">Get started<Icon name="arrow-right" /></Link><Link className="landing-tour" to="/example-report"><span>▶</span>Explore a sample report</Link></div><ul className="landing-benefits"><li><Icon name="check" />CSV, TSV, Excel & JSON</li><li><Icon name="check" />Clear quality checks</li><li><Icon name="check" />Saved analysis reports</li></ul></div>
        <div className="landing-product-scene"><div className="landing-product-preview"><div className="landing-preview-bar"><span className="landing-mini-brand">TS</span><strong>Team Science</strong><span className="landing-preview-label">ILLUSTRATIVE SAMPLE</span></div><div className="landing-preview-title"><div><h2>{sampleReport.filename}</h2><p>{sampleReport.dataset.rows} rows · {sampleReport.dataset.columns} columns</p></div><Link to="/example-report" className="button landing-dark-button">View report<Icon name="arrow-right" /></Link></div><ReportOverview report={sampleReport} preview /></div></div>
      </section>
      <section id="features" className="landing-features" aria-labelledby="features-title"><p className="eyebrow">TURN DATA INTO UNDERSTANDING</p><h2 id="features-title">A cleaner path from data to insight.</h2><div className="landing-feature-grid">{features.map(feature => <Link className="landing-feature" to={feature.to} key={feature.title}><span className={`analysis-icon analysis-${feature.tone}`}><Icon name={feature.icon} /></span><h3>{feature.title}</h3><p>{feature.text}</p><Icon name="arrow-right" /></Link>)}</div></section>
      <section id="workflow" className="landing-workflow" aria-labelledby="workflow-title"><div><p className="eyebrow">A SIMPLE WAY TO START</p><h2 id="workflow-title">From your first upload<br />to your next question.</h2></div><ol><li><span>01</span><div><h3>Bring your dataset</h3><p>Upload a supported file and choose the parsing options that fit your data.</p></div></li><li><span>02</span><div><h3>Understand the findings</h3><p>Review missing values, duplicate rows, outliers, and column summaries.</p></div></li><li><span>03</span><div><h3>Keep exploring</h3><p>Compare columns, generate suggestions, and return to your saved reports.</p></div></li></ol></section>
      <section className="landing-cta"><div><p className="eyebrow">READY FOR CLEARER INSIGHTS?</p><h2>Start turning your data into better questions.</h2><p>Create your workspace and make sense of your next dataset.</p></div><div><Link className="button button-primary" to="/register">Get started<Icon name="arrow-right" /></Link><Link to="/login">Sign in to your account<Icon name="arrow-right" /></Link></div></section>
    </main><footer className="landing-footer"><Link to="/" className="landing-brand"><span>TS</span>Team Science</Link><p>Understand your data. Start with better questions.</p><Link to="/documentation">Documentation<Icon name="arrow-right" /></Link></footer>
  </div>;
}
