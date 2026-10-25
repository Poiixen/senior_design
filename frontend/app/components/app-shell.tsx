import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate, useNavigation } from "react-router";
import { getCurrentUser, logoutUser, type AuthUser } from "~/lib/api";
import { Icon } from "./icon";

export function AppShell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const navigation = useNavigation();
  const navigate = useNavigate();
  const [user, setUser] = useState<AuthUser | null>(null);
  const isAuthPage = pathname === "/login" || pathname === "/register";
  useEffect(() => {
    let active = true;
    if (pathname === "/login" || pathname === "/register") { setUser(null); return () => { active = false; }; }
    getCurrentUser().then(value => { if (active) setUser(value); }).catch(() => { if (active) setUser(null); });
    return () => { active = false; };
  }, [pathname]);
  const initials = user?.email.slice(0, 2).toUpperCase() ?? "TS";
  const isReport = pathname === "/reports" || pathname.startsWith("/reports/");

  if (isAuthPage) {
    return <div className="auth-layout">
      {navigation.state === "loading" && <div className="route-progress auth-route-progress" role="status" aria-label="Loading page" />}
      <Link to="/login" className="auth-brand" aria-label="Team Science login"><span className="brand-mark">TS</span><span><strong>TEAM SCIENCE</strong><small>DATA VALIDATOR</small></span></Link>
      <main className="auth-main" id="main-content" tabIndex={-1}>{children}</main>
    </div>;
  }

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
      <header className="topbar"><div>Workspace <span className="breadcrumb-divider">/</span> <span>{isReport ? "Analysis report" : "Dataset validation"}</span></div><div className="workspace-label"><span className="status-dot" />DATA QUALITY WORKSPACE</div>{user ? <div className="account-controls"><span className="avatar" title={user.email}>{initials}</span><button type="button" className="account-action" onClick={() => void logoutUser().then(() => { setUser(null); navigate("/login"); })}>Log out</button></div> : <Link className="button button-secondary" to="/login">Log in</Link>}</header>
      {navigation.state === "loading" && <div className="route-progress" role="status" aria-label="Loading page" />}
      <main className="main-content" id="main-content" tabIndex={-1}>{children}</main>
    </div>
  </div>;
}
