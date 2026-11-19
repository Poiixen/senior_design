"""Browser request protections shared by all API routes."""

from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse


def session_secret(secret: str | None, secure: bool) -> str:
    import secrets

    if secure and (
        not secret or len(secret) < 32 or "replace-with" in secret.lower()
    ):
        raise ValueError("HTTPS sessions require a random SECRET_KEY of at least 32 characters.")
    return secret or secrets.token_urlsafe(32)


class BrowserSecurity:
    def __init__(self, app, allowed_origins):
        self.app = app
        self.allowed_origins = frozenset(allowed_origins)
        if "*" in self.allowed_origins:
            raise ValueError("Credentialed API access requires explicit CORS origins.")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def secure_send(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "no-referrer"
                if scope["path"].startswith("/api/"):
                    headers["Cache-Control"] = "no-store"
            await send(message)

        if scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
            headers = Headers(scope=scope)
            origin = headers.get("origin")
            referer = headers.get("referer")
            if origin is None and referer is not None:
                try:
                    parsed = urlsplit(referer)
                    origin = f"{parsed.scheme}://{parsed.netloc}"
                except ValueError:
                    origin = "null"
            # Exact configured origins, never an attacker-controlled Host or
            # forwarded header. Headerless non-browser API clients remain usable.
            untrusted = origin is not None and origin not in self.allowed_origins
            missing_browser_origin = origin is None and headers.get("sec-fetch-site") is not None
            if untrusted or missing_browser_origin:
                response = JSONResponse({"detail": "Untrusted request origin."}, status_code=403)
                return await response(scope, receive, secure_send)
        await self.app(scope, receive, secure_send)
