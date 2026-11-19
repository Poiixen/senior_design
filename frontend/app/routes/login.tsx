import { useEffect, useRef } from "react";
import { Form, Link, redirect, useNavigation } from "react-router";
import { ApiError, getCurrentUser, loginUser, getAuthMode } from "~/lib/api";
import { loginDestination } from "~/lib/session";
import type { Route } from "./+types/login";

export function meta() { return [{ title: "Log in | Team Science" }]; }
export async function clientLoader({ request }: Route.ClientLoaderArgs) {
  const mode = await getAuthMode();
  try { await getCurrentUser(); }
  catch (error) {
    if (error instanceof ApiError && error.status === 401) return { mode };
    return { mode, error: "We couldn’t check your existing session. You can try signing in below." };
  }
  throw redirect(loginDestination(request.url));
}
export function HydrateFallback() { return <section className="auth-card panel" role="status"><h1>Checking your session</h1><p className="muted">Opening your workspace if you’re already signed in…</p></section>; }
export async function clientAction({ request }: Route.ClientActionArgs) {
  const data = await request.formData();
  const email = String(data.get("email") ?? "").trim();
  const password = String(data.get("password") ?? "");
  if (!email || !password) return { error: "Access type and password are required." };
  const destination = loginDestination(request.url);
  try {
    const result = await loginUser(email, password);
    return redirect("verification_required" in result ? `/verify-email?next=${encodeURIComponent(destination)}` : destination);
  }
  catch (error) {
    if (error instanceof ApiError && error.status === 503 && data.get("authMode") === "verified") return redirect(`/verify-email?delivery=failed&next=${encodeURIComponent(destination)}`);
    return { error: error instanceof Error ? error.message : "Unable to log in." };
  }
}
export default function Login({ actionData, loaderData }: Route.ComponentProps) {
  const shared = loaderData?.mode === "shared";
  const busy = useNavigation().state !== "idle";
  const submitted = useRef(false);
  useEffect(() => { if (!busy) submitted.current = false; }, [busy]);
  return <section className="auth-card panel"><p className="eyebrow">WELCOME BACK</p><h1>Log in</h1><p className="muted">{shared ? "Choose admin or demo access and enter its password. No email verification is needed." : "Continue to your data-quality workspace."}</p>{loaderData?.error && <p className="notice notice-warning" role="status">{loaderData.error}</p>}<Form method="post" onSubmit={event => { if (busy || submitted.current) event.preventDefault(); else submitted.current = true; }}><input type="hidden" name="authMode" value={shared ? "shared" : "verified"} /><div className="field">{shared ? <><label htmlFor="login-access">Access</label><select id="login-access" name="email" defaultValue="demo"><option value="demo">Demo - explore sample reports</option><option value="admin">Admin - upload and analyze</option></select></> : <><label htmlFor="login-email">Email</label><input id="login-email" name="email" type="email" autoComplete="email" required /></>}</div><div className="field"><label htmlFor="login-password">Password</label><input id="login-password" name="password" type="password" autoComplete="current-password" required /></div>{actionData?.error && <p className="notice notice-error" role="alert">{actionData.error}</p>}<button className="button button-primary" disabled={busy} type="submit">{busy ? "Logging in…" : "Log in"}</button></Form>{shared ? <p className="muted">Ask the project team for the demo password.</p> : <p>New to Team Science? <Link to="/register">Create an account</Link>.</p>}</section>;
}
