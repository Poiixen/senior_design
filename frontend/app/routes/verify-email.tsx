import { getAuthMode } from "~/lib/api";
import { Form, Link, redirect, useNavigation, useSearchParams } from "react-router";
import { resendVerification, verifyEmail } from "~/lib/api";
import { loginDestination } from "~/lib/session";
import type { Route } from "./+types/verify-email";

export function meta() { return [{ title: "Verify your email | Team Science" }]; }
export async function clientAction({ request }: Route.ClientActionArgs) {
  const form = await request.formData();
  try {
    if (form.get("intent") === "resend") {
      await resendVerification();
      return { message: "A new code has been sent. Only the newest code will work." };
    }
    await verifyEmail(String(form.get("code") ?? "").trim());
    return redirect(loginDestination(request.url));
  } catch (error) {
    return { error: error instanceof Error ? error.message : "Unable to verify your email." };
  }
}
export default function VerifyEmail({ actionData }: Route.ComponentProps) {
  const busy = useNavigation().state !== "idle";
  const [params] = useSearchParams();
  return <section className="auth-card panel">
    <p className="eyebrow">ONE MORE STEP</p><h1>Verify your email</h1>
    <p className="muted">Enter the 8-digit code sent to your email. Your account stays locked until you confirm it. Codes expire in 10 minutes.</p>
    {params.get("delivery") === "failed" && !actionData?.message && <p className="notice notice-error" role="alert">We couldn't send your code. Try resending, or contact the site owner if this continues.</p>}
    {actionData?.error && <p className="notice notice-error" role="alert">{actionData.error}</p>}
    {actionData?.message && <p className="notice" role="status">{actionData.message}</p>}
    <Form method="post"><div className="field"><label htmlFor="verification-code">Verification code</label><input id="verification-code" name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{8}" minLength={8} maxLength={8} required /></div><button className="button button-primary" type="submit" disabled={busy}>{busy ? "Please wait…" : "Verify email"}</button></Form>
    <Form method="post"><button className="button" type="submit" name="intent" value="resend" disabled={busy}>Resend code</button></Form>
    <p>Check your spam folder. If you closed the original browser or need a different email, <Link to="/login">sign in again</Link> or <Link to="/register">create an account</Link>.</p>
  </section>;
}

export async function clientLoader() {
  if (await getAuthMode() === "shared") throw redirect("/login");
  return null;
}
export function HydrateFallback() { return <p role="status">Checking access...</p>; }
