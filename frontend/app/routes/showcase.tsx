import { Form, Link, redirect, useNavigation } from "react-router";
import { requestJson } from "~/lib/api";
import type { Route } from "./+types/showcase";
import "./showcase.css";

export function meta() { return [{ title: "Try Team Science" }]; }
export async function clientAction() {
  try {
    await requestJson("/api/auth/demo", { method: "POST", signal: AbortSignal.timeout(20000) });
    return redirect("/showcase/report");
  } catch (error) {
    return { error: error instanceof Error ? error.message : "Demo unavailable. Please try again." };
  }
}

export default function Showcase({ actionData }: Route.ComponentProps) {
  const busy = useNavigation().state !== "idle";
  return <main id="showcase-content" className="showcase"><p className="eyebrow">TEAM SCIENCE SHOWCASE</p>
    <h1>Understand your data without coding.</h1>
    <p>See how a few simple checks turn a table of data into useful questions.</p>
    <Form method="post"><button className="button button-primary" disabled={busy}>{busy ? "Opening demo…" : "Try Demo"}</button></Form>
    {actionData?.error && <p role="alert" className="notice notice-error">{actionData.error} You can retry or <Link to="/example-report">view the offline sample</Link>.</p>}
    <p>No upload or password needed. Try Demo switches this browser to a shared, read-only example.</p>
    <nav aria-label="Account options"><Link to="/login">Log In</Link><Link to="/register">Upload Your Own Data</Link></nav>
    <ol><li>Spot missing values.</li><li>Compare two groups.</li><li>See what to check next.</li></ol>
  </main>;
}
