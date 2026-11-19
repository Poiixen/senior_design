export const authenticationPaths = new Set(["/login", "/register", "/verify-email"]);
export function isAuthenticationPath(path: string) {
  return authenticationPaths.has(path.replace(/\/+$/, "") || "/");
}
export function signInLocation(url: URL) {
  return `/login?next=${encodeURIComponent(url.pathname + url.search)}`;
}
