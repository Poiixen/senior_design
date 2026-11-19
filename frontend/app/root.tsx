import {
  isRouteErrorResponse,
  Links,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
  Link,
  redirect,
  useRevalidator,
} from "react-router";

import type { Route } from "./+types/root";
import "./app.css";
import { PreferencesProvider } from "./components/preferences-provider";
import { AccountProvider } from "./components/account-provider";
import { initializeAppearance } from "./lib/preferences";
import "./theme.css";
import "./components/navigation.css";
import { requireWebsiteAccess } from "./lib/access.server";
import { isAuthenticationPath, signInLocation } from "./lib/access";
import { ApiError, getCurrentUser } from "./lib/api";

export async function loader({ request }: Route.LoaderArgs) {
  return requireWebsiteAccess(request);
}
export async function clientLoader({ request }: Route.ClientLoaderArgs) {
  const url = new URL(request.url);
  if (isAuthenticationPath(url.pathname)) return null;
  try { await getCurrentUser(); }
  catch (error) {
    if (error instanceof ApiError && error.status === 401) throw redirect(signInLocation(url));
    throw error;
  }
  return null;
}
clientLoader.hydrate = true as const;
export function shouldRevalidate() { return true; }
export function headers() { return { "Cache-Control": "no-store" }; }
export function HydrateFallback() {
  return <main className="standalone-error panel" role="status"><h1>Checking your session</h1><p>Verifying access before opening Team Science.</p></main>;
}

export const links: Route.LinksFunction = () => [
  { rel: "preconnect", href: "https://fonts.googleapis.com" },
  {
    rel: "preconnect",
    href: "https://fonts.gstatic.com",
    crossOrigin: "anonymous",
  },
  {
    rel: "stylesheet",
    href: "https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,100..900;1,14..32,100..900&display=swap",
  },
];

export function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <script dangerouslySetInnerHTML={{ __html: `(${initializeAppearance.toString()})();` }} />
        <Meta />
        <Links />
      </head>
      <body>
        {children}
        <ScrollRestoration />
        <Scripts />
      </body>
    </html>
  );
}

export default function App() {
  return <PreferencesProvider><AccountProvider><Outlet /></AccountProvider></PreferencesProvider>;
}

export function ErrorBoundary({ error }: Route.ErrorBoundaryProps) {
  const revalidator = useRevalidator();
  let message = "Unable to open this page";
  let details = "Please try again or return to the home page.";
  let stack: string | undefined;

  if (isRouteErrorResponse(error)) {
    message = error.status === 404 ? "404" : "Error";
    details =
      error.status === 404
        ? "The requested page could not be found."
        : error.statusText || details;
  } else if (import.meta.env.DEV && error && error instanceof Error) {
    details = error.message;
    stack = error.stack;
  }
  if (error instanceof ApiError || (isRouteErrorResponse(error) && error.status === 503)) {
    message = "Unable to verify access";
    details = "We couldn't confirm your session. Try again or sign in to continue.";
  }

  return (
    <main className="standalone-error panel">
      <h1>{message}</h1>
      <p>{details}</p>
      <button className="button button-primary" type="button" disabled={revalidator.state !== "idle"} onClick={() => void revalidator.revalidate()}>Try again</button>
      <Link className="button" to="/login">Sign in</Link>
      <Link className="button button-primary" to="/">Back to home</Link>
      {stack && (
        <pre className="w-full p-4 overflow-x-auto">
          <code>{stack}</code>
        </pre>
      )}
    </main>
  );
}
