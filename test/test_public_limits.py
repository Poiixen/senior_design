from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.api.public_limits import PublicLimits


def test_auth_rate_limit_does_not_block_health_or_other_request_family():
    app = FastAPI()
    app.add_middleware(PublicLimits)
    @app.post("/api/auth/login")
    def login():
        return {}
    @app.post("/api/analyze")
    def analyze():
        return {}
    @app.get("/health")
    def health():
        return {"status": "ok"}
    with TestClient(app) as client:
        for _ in range(20):
            assert client.post("/api/auth/login").status_code == 200
        blocked = client.post("/api/auth/login")
        assert blocked.status_code == 429
        assert blocked.headers["retry-after"] == "60"
        assert client.get("/health").status_code == 200
        assert client.post("/api/analyze").status_code == 200
