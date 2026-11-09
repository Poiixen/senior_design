# Navigation and settings

The public homepage is `/`. It presents the same marketing content and Sign in
entry point to everyone, without account controls. Sign in checks the existing
session and opens the product without asking for credentials again when it is
still valid. The product overview is `/dashboard`, uploading is `/upload`, and
account/display preferences are at the authenticated `/settings` route. Product
navigation starts at Overview; there is no Home item, and its logo opens the
overview.

## Session inactivity

Sessions expire after five minutes of inactivity. The API enforces a 300-second
signed-cookie lifetime and validates the last authenticated activity timestamp.
Legacy sessions without that timestamp require a fresh sign-in. Browser input
renews active sessions using the existing current-user endpoint, throttled to
once a minute; idle pages never send periodic keepalive requests. The browser
also clears the session and returns protected screens to sign-in after five
idle minutes, checking again when a suspended tab resumes. Same-origin tabs
share activity and expiration through an ephemeral BroadcastChannel. No tokens
or account details are written to localStorage.

Desktop navigation expands or collapses into an icon rail. Mobile navigation
uses a modal drawer with native focus containment, Escape dismissal, an explicit
close button, and focus restoration. The desktop collapse preference does not
affect the mobile drawer.

## Browser preferences

`team-science.preferences.v1` in localStorage contains only these UI preferences:

| Preference | Default | Supported values |
| --- | --- | --- |
| Theme | System | System, Light, Dark |
| Accent color | Violet | Violet, Blue, Teal, Rose, Amber |
| Density | Comfortable | Comfortable, Compact |
| Motion | System | System, Reduce, Full |
| Report sort | Newest first | Newest/oldest, most/fewest issues, most/fewest rows |
| Sidebar collapsed | No | Yes, No |

Preferences are validated on read, synchronized between tabs, and applied
immediately. Invalid or unavailable storage falls back to defaults. System
appearance and motion track device changes. An inline initialization script
applies stored appearance before the page paints. No account credentials,
profile information, or report data are stored in this preference key.

Saved Reports uses the configured sorting default. Changing sorting in that
view does not overwrite the default. Search and status filtering operate on
the existing reports response without new backend endpoints. Resetting all
preferences requires confirmation and does not modify reports or account state.

## Verification

Run commands from `frontend`:

```text
npm run typecheck
npm test
npm run test:e2e
```

Both test commands build the application first. Browser tests use isolated
mock account/report responses and a local production server on port 5186.
They use installed Chrome by default. To use Playwright's installed Chromium,
set `PLAYWRIGHT_CHANNEL=chromium` before running the browser tests.

Screenshots and failure traces are written under the ignored `.run` directory.
