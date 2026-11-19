# Security controls

## Current deployment: admin and demo passwords

`AUTH_MODE=shared` is now the default. The login screen offers Admin and Demo,
each with its own password. Registration and email verification endpoints are
closed in this mode; existing personal accounts cannot access the product.
Their data is preserved. Admin can upload and analyze its own datasets. Demo
can read the seeded sample reports and deterministic suggestions, but cannot
write or use AI chat. Admin does not gain access to other users' private reports.

After rebuilding/loading both images, set `AUTH_MODE=shared` in the server
`.env`, stop the API, and configure passwords interactively:

```bash
docker compose -f compose.small.yaml stop api
docker compose -f compose.small.yaml run --rm --no-deps api python -m scripts.setup_shared_access
docker compose -f compose.small.yaml up -d --no-build --pull never
```

The setup command asks for two different non-empty passwords,
stores only Argon2 hashes, seeds/reuses the demo data, and revokes existing
shared sessions. Run it again to rotate passwords. No SMTP is needed in shared
mode. Back up the data volume before rollout; preserve `.env` and the volume.
No default passwords are shipped. Both images must be rebuilt, and the API
image must include `scripts/setup_shared_access.py`.

Session expiry, logout revocation, rate limits, report ownership, HTTPS cookies,
and browser request protections still apply. The email-verification workflow
below is retained for a later `AUTH_MODE=verified` deployment.

## Optional verified-account mode

The website requires login and email verification before any product page is
rendered, including the homepage, documentation, and examples. Only `/login`,
`/register`, and `/verify-email` are public pages. The server checks sessions with
the API before rendering; client navigation also rechecks. An unavailable API
blocks access. API docs are disabled; `/health` remains a minimal public probe.
Static JavaScript/CSS assets remain public and must never contain secrets.

All app APIs use `get_current_user`, which checks a database-backed session and
verified email on every request, followed by the existing report ownership checks.
Email verification is required, not optional. The demo endpoint no longer grants
sessions, even if an old deployment sets `SHOWCASE_ENABLED=true`.

Passwords use Argon2; new passwords require at least 15 characters. Existing
passwords still work, but legacy users must verify email before accessing data.
New security tables are created without rewriting users or reports. Old cookies
are invalidated by the switch to opaque session tokens.

Verification uses an eight-digit, cryptographically generated code bound to the
requesting browser. Only a keyed hash is stored. Codes expire in ten minutes,
allow five attempts, and are consumed atomically; resending invalidates the old
code. Delivery is limited to three messages per account per 15 minutes. Login and
registration share limits of ten attempts per account and sixty per IP per 15
minutes. Verification attempts are additionally limited to thirty per IP. These
counters live in SQLite and survive restarts and multiple API processes.

Signed HttpOnly cookies carry opaque tokens; their hashes live in the database.
Sessions expire after five idle minutes or twelve hours total. Logout revokes the
server record, so copying an old cookie does not bypass logout. The ten-minute
cookie lifetime permits completing verification; it does not extend authenticated
access past the server's five-minute idle limit.

## Email delivery and rollout

Configure the following in the deployment `.env` (never commit credentials):

```dotenv
SMTP_HOST=your-provider-smtp-host
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_FROM=Team Science <verified-sender@your-domain.example>
SMTP_USERNAME=your-provider-username
SMTP_PASSWORD=your-provider-password
```

Use `SMTP_SECURITY=ssl` and port 465 if your provider requires implicit TLS.
Plaintext SMTP is rejected. Complete the provider's sender/domain verification
and DNS setup. Both Compose files pass these values to the API. SMTP failures
leave accounts locked and offer resend; codes are never returned by an API or
written to logs. For local testing use the captured test outbox in pytest; there
is no production verification bypass.

The frontend server needs `API_INTERNAL_URL=http://api:8000` in Docker (already
set in both Compose files); local default is `http://127.0.0.1:8000`. This must be
a trusted internal API origin because it receives the session cookie. Never derive
it from a visitor's Host header. Keep the API port inaccessible from the internet.
Set `SECRET_KEY`, `SESSION_COOKIE_SECURE=true`, and the exact HTTPS
`CORS_ALLOWED_ORIGINS` as before.

Before releasing, back up the SQLite database, configure SMTP, rebuild both
application images, and test registration, delivered email, verification, login,
logout, and reload using the real HTTPS domain. Existing deployment archives must
be rebuilt; they do not automatically include these changes. Users with obsolete
or inaccessible email addresses cannot complete verification; an audited account
recovery process is still needed before charging customers.

## Future paid access

Billing is not enabled and no charges are made. Add a separate server-maintained
subscription/entitlement record keyed to `users.id`, and enforce it after verified
authentication for every paid API and website route. Keep login, verification,
checkout, and billing management reachable when a subscription expires. Use
provider-hosted checkout and verified, idempotent webhooks to update entitlement;
never trust a browser flag or checkout success URL as proof of payment. Pricing,
trial policy, grace periods, refunds, and the payment provider remain undecided.

## Other controls

Write requests with Origin or Referer headers must match an exact entry in
`CORS_ALLOWED_ORIGINS`. Include every legitimate frontend origin (scheme, host,
and port; no paths or trailing slash). Wildcard origins are rejected. Browser
requests carrying Fetch Metadata but neither source header are rejected.
Headerless CLI clients remain supported; this is a compatibility exception,
not authentication. Older browsers that omit all these headers rely on the
session cookie's SameSite=Lax protection.

API responses include `Cache-Control: no-store`, MIME sniffing protection,
frame denial, and a no-referrer policy. The production Caddy configuration adds
these browser protections to frontend pages, plus HSTS and a limited CSP that
blocks framing, objects, and foreign base URLs. It does not yet enforce a full
script policy.

With `SESSION_COOKIE_SECURE=true`, startup requires a SECRET_KEY of at least
32 characters and rejects the deployment template placeholder. Generate a
random key with `openssl rand -hex 32`; length validation cannot measure entropy.
Rotating this key invalidates existing cookies. Local development may use a
temporary random key. Never commit real keys.

Excel uploads are checked before parsing: at most 2,000 ZIP members and 50 MiB
of declared expanded content, with encrypted archives rejected. This reduces
compressed-upload abuse; it is not a complete memory bound for parsed data.

Keep the API private behind Caddy. Its existing body limit and the API's upload
limit protect different stages of processing. Production enables
`PUBLIC_RATE_LIMITS=true`; those general write counters require one API worker.
Authentication limits are separate and database-backed. Multiple workers or
replicas need a shared general write-rate store. Proxy-header trust
assumes the API cannot be reached directly by untrusted clients.

Regression checks: `python -m pytest test/test_verified_access.py test/test_security.py test/test_authentication.py
test/test_report_authorization.py test/test_dataset_loader.py test/test_public_limits.py`.

References: [OWASP CSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
and [OWASP file uploads](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html).
Authentication/session design references: [OWASP authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
and [OWASP sessions](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
