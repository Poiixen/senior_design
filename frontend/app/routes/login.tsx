import { useState } from "react";
import { Form, Link, redirect, useNavigation } from "react-router";
import { loginUser } from "~/lib/api";
import type { Route } from "./+types/login";

export function meta() { return [{ title: "Log in | Team Science" }]; }
export async function clientAction({ request }: Route.ClientActionArgs) {
  const data = await request.formData();
  const email = String(data.get("email") ?? "").trim();
  const password = String(data.get("password") ?? "");
  if (!email || !password) return { error: "Email and password are required." };
  const requested = new URL(request.url).searchParams.get("next");
  const destination = requested?.startsWith("/") && !requested.startsWith("//") ? requested : "/";
  try { await loginUser(email, password); return redirect(destination); }
  catch (error) { return { error: error instanceof Error ? error.message : "Unable to log in." }; }
}
export default function Login({ actionData }: Route.ComponentProps) {
  const busy = useNavigation().state !== "idle"; const [submitted, setSubmitted] = useState(false);
  return <section className="auth-card panel"><p className="eyebrow">WELCOME BACK</p><h1>Log in</h1><p className="muted">Continue to your data-quality workspace.</p><Form method="post" onSubmit={event => { if (busy || submitted) event.preventDefault(); else setSubmitted(true); }}><div className="field"><label htmlFor="login-email">Email</label><input id="login-email" name="email" type="email" autoComplete="email" required /></div><div className="field"><label htmlFor="login-password">Password</label><input id="login-password" name="password" type="password" autoComplete="current-password" required /></div>{actionData?.error && <p className="notice notice-error" role="alert">{actionData.error}</p>}<button className="button button-primary" disabled={busy} type="submit">{busy ? "Logging in…" : "Log in"}</button></Form><p>New to Team Science? <Link to="/register">Create an account</Link>.</p></section>;
}
