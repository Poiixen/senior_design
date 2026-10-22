import { useState } from "react";
import { Form, Link, redirect, useNavigation } from "react-router";
import { registerUser } from "~/lib/api";
import type { Route } from "./+types/register";

export function meta() { return [{ title: "Register | Team Science" }]; }
export async function clientAction({ request }: Route.ClientActionArgs) {
  const data = await request.formData(); const email = String(data.get("email") ?? "").trim(); const password = String(data.get("password") ?? ""); const confirmation = String(data.get("confirmation") ?? "");
  if (!email || !password) return { error: "Email and password are required." };
  if (password !== confirmation) return { error: "Passwords do not match." };
  try { await registerUser(email, password); return redirect("/"); } catch (error) { return { error: error instanceof Error ? error.message : "Unable to register." }; }
}
export default function Register({ actionData }: Route.ComponentProps) {
  const busy = useNavigation().state !== "idle"; const [submitted, setSubmitted] = useState(false);
  return <section className="auth-card panel"><p className="eyebrow">CREATE YOUR WORKSPACE</p><h1>Register</h1><p className="muted">Create an account to save and revisit your reports.</p><Form method="post" onSubmit={event => { if (busy || submitted) event.preventDefault(); else setSubmitted(true); }}><div className="field"><label htmlFor="register-email">Email</label><input id="register-email" name="email" type="email" autoComplete="email" required /></div><div className="field"><label htmlFor="register-password">Password</label><input id="register-password" name="password" type="password" autoComplete="new-password" minLength={8} required /></div><div className="field"><label htmlFor="register-confirmation">Confirm password</label><input id="register-confirmation" name="confirmation" type="password" autoComplete="new-password" minLength={8} required /></div>{actionData?.error && <p className="notice notice-error" role="alert">{actionData.error}</p>}<button className="button button-primary" disabled={busy} type="submit">{busy ? "Creating account…" : "Create account"}</button></Form><p>Already registered? <Link to="/login">Log in</Link>.</p></section>;
}
