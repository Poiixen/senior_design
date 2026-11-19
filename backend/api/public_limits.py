"""Bounded single-process public request limits. Run one API worker."""
from collections import OrderedDict
from time import monotonic

from starlette.responses import JSONResponse


class PublicLimits:
    def __init__(self, app):
        self.app = app
        self.buckets = OrderedDict()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] not in ("GET", "HEAD", "OPTIONS"):
            path = scope["path"]
            category = "auth" if path.startswith("/api/auth/") else "write"
            key = ((scope.get("client") or ("unknown",))[0], category)
            now = monotonic()
            start, count = self.buckets.pop(key, (now, 0))
            if now - start >= 60:
                start, count = now, 0
            self.buckets[key] = (start, count + 1)
            while len(self.buckets) > 10000:
                self.buckets.popitem(last=False)
            if count >= (20 if category == "auth" else 30):
                response = JSONResponse({"detail": "Too many requests. Please wait a minute and try again."},
                    status_code=429, headers={"Retry-After": "60"})
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
