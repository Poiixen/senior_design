import type { ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigation } from "react-router";
import { Icon } from "./icon";

export function AppShell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const navigation = useNavigation();
  const isReport = pathname === "/reports" || pathname.startsWith("/reports/");

  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <aside className="sidebar">
      <Link to="/" className="brand" aria-label="Team Science home">
        <span className="brand-mark">TS</span><span><strong>TEAM SCIENCE</strong><small>DATA VALIDATOR</small></span>
      </Link>
      <div className="nav-label">WORKSPACE</div>
      <nav className="workspace-nav" aria-label="Workspace">
        <NavLink to="/" end><Icon name="upload" />Upload dataset</NavLink>
        <NavLink to="/reports"><Icon name="report" />Reports</NavLink>
        <NavLink to="/documentation"><Icon name="help" />Documentation</NavLink>
      </nav>
      <div className="sidebar-footer"><strong>TEAM SCIENCE</strong><span>Understand your data.</span><span>Start with better questions.</span></div>
    </aside>
    <div className="workspace">
      <header className="topbar"><div>Workspace <span className="breadcrumb-divider">/</span> <span>{isReport ? "Analysis report" : "Dataset validation"}</span></div><div className="workspace-label"><span className="status-dot" />DATA QUALITY WORKSPACE</div><span className="avatar" aria-label="Team Science workspace">TS</span></header>
      {navigation.state === "loading" && <div className="route-progress" role="status" aria-label="Loading page" />}
      <main className="main-content" id="main-content" tabIndex={-1}>{children}</main>
    </div>
  </div>;
}
