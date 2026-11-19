# Security controls

The API uses Argon2 password hashing, signed HttpOnly sessions with a five-minute
idle timeout, and ownership checks for saved reports and their related resources.

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
`PUBLIC_RATE_LIMITS=true`; its in-memory per-IP counters require one API worker.
Multiple workers or replicas need a shared rate-limit store. Proxy-header trust
assumes the API cannot be reached directly by untrusted clients.

Regression checks: `python -m pytest test/test_security.py test/test_authentication.py
test/test_report_authorization.py test/test_dataset_loader.py test/test_public_limits.py`.

References: [OWASP CSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
and [OWASP file uploads](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html).
