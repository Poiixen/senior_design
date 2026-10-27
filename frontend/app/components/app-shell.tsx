import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigation } from "react-router";
import { useAccount } from "./account-provider";
import { usePreferences } from "./preferences-provider";
import { Icon } from "./icon";

export function AppShell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const navigation = useNavigation();
  const account = useAccount();
  const { preferences, update } = usePreferences();
  const drawer = useRef<HTMLDialogElement>(null);
  const menu = useRef<HTMLButtonElement>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const isAuthPage = pathname === "/login" || pathname === "/register";
  const initials = account.user?.email.slice(0, 2).toUpperCase() ?? "TS";
  const closeDrawer = () => { drawer.current?.close(); setMobileOpen(false); };
  useEffect(() => { drawer.current?.close(); setMobileOpen(false); }, [pathname]);
  useEffect(() => {
    const desktop = matchMedia("(min-width: 761px)");
    const handleResize = () => { if (desktop.matches) { drawer.current?.close(); setMobileOpen(false); } };
    desktop.addEventListener("change", handleResize);
    return () => desktop.removeEventListener("change", handleResize);
  }, []);
  useEffect(() => {
    if (!mobileOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previous; };
  }, [mobileOpen]);

  if (pathname === "/") return <><a className="skip-link" href="#main-content">Skip to content</a>{children}</>;
  if (isAuthPage) return <div className="auth-layout">
    {navigation.state === "loading" && <div className="route-progress auth-route-progress" role="status" aria-label="Loading page" />}
    <Link to="/" className="auth-brand" aria-label="Team Science home"><span className="brand-mark">TS</span><span><strong>TEAM SCIENCE</strong><small>DATA VALIDATOR</small></span></Link>
    <main className="auth-main" id="main-content" tabIndex={-1}>{children}</main>
  </div>;

  const sidebarContent = (mobile = false) => <>
    <div className="sidebar-header"><Link to="/dashboard" className="brand" aria-label="Team Science overview" title="Team Science overview"><span className="brand-mark">TS</span><span className="nav-copy"><strong>Team Science</strong><small>DATA WORKSPACE</small></span></Link>
      {mobile ? <button type="button" className="icon-button" onClick={closeDrawer} aria-label="Close navigation"><Icon name="x" /></button> : <button type="button" className="icon-button sidebar-toggle" onClick={() => update({ sidebarCollapsed: !preferences.sidebarCollapsed })} aria-expanded={!preferences.sidebarCollapsed} aria-controls="desktop-navigation" aria-label={preferences.sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"} title={preferences.sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}><Icon name={preferences.sidebarCollapsed ? "expand" : "collapse"} /></button>}
    </div>
    <p className="nav-label nav-copy">WORKSPACE</p>
    <nav className="workspace-nav" aria-label={mobile ? "Mobile workspace" : "Workspace"} id={mobile ? "mobile-navigation" : "desktop-navigation"} onClick={event => { if (mobile && (event.target as HTMLElement).closest("a")) closeDrawer(); }}>
      <NavLink to="/dashboard" title="Overview" aria-label="Overview"><Icon name="chart" /><span className="nav-copy">Overview</span></NavLink>
      <NavLink to="/upload" title="Upload Dataset" aria-label="Upload Dataset"><Icon name="upload" /><span className="nav-copy">Upload Dataset</span></NavLink>
      <NavLink to="/reports" title="Saved Reports" aria-label="Saved Reports"><Icon name="report" /><span className="nav-copy">Saved Reports</span></NavLink>
      <NavLink to="/documentation" title="Documentation" aria-label="Documentation"><Icon name="help" /><span className="nav-copy">Documentation</span></NavLink>
    </nav>
    <div className="sidebar-account"><p className="nav-label nav-copy">ACCOUNT</p><nav className="workspace-nav" aria-label={mobile ? "Mobile account" : "Account"}><NavLink to="/settings" title="Settings" aria-label="Settings" onClick={mobile ? closeDrawer : undefined}><Icon name="settings" /><span className="nav-copy">Settings</span></NavLink></nav>
      <div className="sidebar-theme"><label className="nav-copy" htmlFor={mobile ? "mobile-theme" : "sidebar-theme"}>Appearance</label><select id={mobile ? "mobile-theme" : "sidebar-theme"} aria-label="Appearance theme" value={preferences.theme} onChange={event => update({ theme: event.target.value as typeof preferences.theme })}><option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option></select></div>
      <button className="icon-button rail-theme" type="button" title={`Theme: ${preferences.theme}`} aria-label={`Theme: ${preferences.theme}. Switch to ${preferences.theme === "system" ? "light" : preferences.theme === "light" ? "dark" : "system"}`} onClick={() => update({ theme: preferences.theme === "system" ? "light" : preferences.theme === "light" ? "dark" : "system" })}><Icon name="bulb" /></button>
      {account.user ? <><Link to="/settings" className="sidebar-user" title={account.user.email} aria-label={`Account settings for ${account.user.email}`} onClick={mobile ? closeDrawer : undefined}><span className="avatar">{initials}</span><span className="nav-copy"><strong>Your workspace</strong><span>{account.user.email}</span></span></Link><button type="button" className="sidebar-logout" title="Log out" aria-label="Log out" disabled={account.loggingOut} onClick={() => void account.logout()}><Icon name="logout" /><span className="nav-copy">{account.loggingOut ? "Logging out…" : "Log out"}</span></button></> : <Link to="/login" className="sidebar-logout" title="Sign in" aria-label="Sign in"><Icon name="users" /><span className="nav-copy">{account.loading ? "Checking account…" : "Sign in"}</span></Link>}
    </div>
  </>;
  const pageLabel = pathname === "/dashboard" ? "Overview" : pathname === "/settings" ? "Settings" : pathname.startsWith("/reports/") ? "Analysis report" : pathname === "/reports" ? "Saved reports" : pathname === "/upload" ? "Upload dataset" : "Documentation";
  return <div className={`app-shell ${preferences.sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
    <a className="skip-link" href="#main-content">Skip to content</a>
    <aside className="sidebar desktop-sidebar" aria-label="Application navigation">{sidebarContent()}</aside>
    <dialog ref={drawer} className="mobile-drawer" aria-label="Application navigation" onClose={() => { setMobileOpen(false); menu.current?.focus(); }} onClick={event => { if (event.target === event.currentTarget) closeDrawer(); }}><div className="mobile-drawer-content">{sidebarContent(true)}</div></dialog>
    <div className="workspace"><header className="topbar"><button ref={menu} type="button" className="icon-button mobile-menu" aria-label="Open navigation" aria-expanded={mobileOpen} aria-controls="mobile-navigation" onClick={() => { drawer.current?.showModal(); setMobileOpen(true); }}><Icon name="menu" /></button><div className="workspace-breadcrumb"><Link to="/dashboard">Workspace</Link><span className="breadcrumb-divider">/</span><span>{pageLabel}</span></div><Link className="topbar-account" to={account.user ? "/settings" : "/login"} aria-label={account.user ? `Account settings for ${account.user.email}` : "Sign in"}><span className="avatar" title={account.user?.email}>{initials}</span></Link></header>
      {account.error && <div className="account-notice notice notice-error" role="alert"><span>{account.error}</span><button type="button" onClick={account.refresh}>Retry account</button></div>}
      {navigation.state === "loading" && <div className="route-progress" role="status" aria-label="Loading page" />}
      <main className="main-content" id="main-content" tabIndex={-1}>{children}</main>
    </div>
  </div>;
}
