import { data, redirect } from "react-router";
import { isAuthenticationPath, signInLocation } from "./access";

export async function requireWebsiteAccess(request: Request) {
  const url = new URL(request.url);
  const headers = new Headers({ "Cache-Control": "no-store" });
  if (isAuthenticationPath(url.pathname)) return data(null, { headers });
  const cookie = request.headers.get("Cookie");
  if (!cookie) throw redirect(signInLocation(url), { headers });
  // Fixed server configuration; never forward cookies to a request Host value.
  const base = process.env.API_INTERNAL_URL || "http://127.0.0.1:8000";
  let response: Response;
  try {
    response = await fetch(new URL("/api/auth/me", base), {
      headers: { Cookie: cookie }, signal: AbortSignal.timeout(10000), redirect: "error",
    });
  } catch {
    throw new Response("Unable to verify access. Please try again shortly.", { status: 503, headers });
  }
  const renewedCookie = response.headers.get("set-cookie");
  if (renewedCookie) headers.append("Set-Cookie", renewedCookie);
  if (response.status === 401) throw redirect(signInLocation(url), { headers });
  if (!response.ok) throw new Response("Unable to verify access.", { status: 503, headers });
  return data(null, { headers });
}
