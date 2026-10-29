import { Link, Outlet, redirect, useRevalidator } from "react-router";
import { AppShell } from "~/components/app-shell";
import { ApiError, getCurrentUser } from "~/lib/api";
import type { Route } from "./+types/workspace";

export async function clientLoader({ request }: Route.ClientLoaderArgs) {
  try { return { user: await getCurrentUser() }; }
  catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      const url = new URL(request.url);
      throw redirect(`/login?next=${encodeURIComponent(url.pathname + url.search)}`);
    }
    throw error;
  }
}

// Recheck the session before every workspace navigation, including report tabs.
export function shouldRevalidate() { return true; }
export function HydrateFallback() {
  return <main className="standalone-error panel" role="status" aria-busy="true"><h1>Checking your session</h1><p className="muted">Verifying access to your workspace.</p></main>;
}
export default function Workspace() { return <AppShell><Outlet /></AppShell>; }
export function ErrorBoundary() {
  const revalidator = useRevalidator();
  return <main className="standalone-error panel" role="alert"><h1>Unable to verify workspace access</h1><p>Please retry or sign in to continue.</p><button className="button button-primary" type="button" disabled={revalidator.state !== "idle"} onClick={() => void revalidator.revalidate()}>Try again</button> <Link to="/login">Sign in</Link> <Link to="/">Back to home</Link></main>;
}
