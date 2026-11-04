export const SESSION_IDLE_MS = 5 * 60 * 1000;
export const ACTIVITY_SYNC_MS = 60 * 1000;

export function loginDestination(url: string): string {
  const current = new URL(url);
  const requested = current.searchParams.get("next");
  if (!requested?.startsWith("/") || requested.startsWith("//")) return "/dashboard";
  const destination = new URL(requested, current);
  if (destination.origin !== current.origin || ["/login", "/register"].includes(destination.pathname)) return "/dashboard";
  return destination.pathname + destination.search + destination.hash;
}
