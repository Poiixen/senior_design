import pytest

from backend.api.main import app
from conftest import register_user
from scripts.setup_shared_access import configure_accounts
from backend.services.showcase import showcase_report

ADMIN_PASSWORD = "admin-password-for-tests"
DEMO_PASSWORD = "demo-password-for-tests"


@pytest.fixture
def shared(client, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "shared")
    configure_accounts(app.state.analysis_service, ADMIN_PASSWORD, DEMO_PASSWORD)
    return client


def sign_in(client, role, password):
    return client.post("/api/auth/login", json={"email": role, "password": password})


def test_admin_can_upload_and_logout_revokes_session(shared):
    assert sign_in(shared, "admin", ADMIN_PASSWORD).status_code == 200
    assert shared.get("/api/auth/me").status_code == 200
    assert shared.post("/api/analyze", files={"file": ("data.csv", b"x,y\n1,2\n3,4\n", "text/csv")}).status_code == 200
    cookie = shared.cookies.get("session")
    assert shared.post("/api/auth/logout").status_code == 200
    shared.cookies.set("session", cookie)
    assert shared.get("/api/auth/me").status_code == 401


def test_demo_can_read_but_cannot_upload(shared):
    assert sign_in(shared, "demo", ADMIN_PASSWORD).status_code == 401
    assert sign_in(shared, "demo", DEMO_PASSWORD).status_code == 200
    reports = shared.get("/api/reports")
    assert reports.status_code == 200
    _, report_id = showcase_report(app.state.analysis_service)
    assert shared.get(f"/api/reports/{report_id}").status_code == 200
    assert shared.post(f"/api/reports/{report_id}/suggestions", json={"limit": 5}).status_code == 200
    for path, payload in [("comparisons", {"comparison_type": "categorical_numeric", "column_a": "workshop", "column_b": "minutes"}), ("conversations", {}), ("questions", {"question": "Explain this report"})]:
        assert shared.post(f"/api/reports/{report_id}/{path}", json=payload).status_code == 403
    assert shared.post("/api/analyze", files={"file": ("data.csv", b"x\n1\n", "text/csv")}).status_code == 403
    configure_accounts(app.state.analysis_service, ADMIN_PASSWORD, DEMO_PASSWORD + "rotated")
    assert shared.get("/api/auth/me").status_code == 401
    assert sign_in(shared, "demo", DEMO_PASSWORD).status_code == 401
    assert sign_in(shared, "admin", ADMIN_PASSWORD).status_code == 200
    assert shared.get(f"/api/reports/{report_id}").status_code == 404


def test_shared_closes_other_entry_points(shared):
    assert shared.get("/api/auth/config").json() == {"mode": "shared"}
    assert shared.post("/api/auth/register", json={"email": "someone@example.com", "password": ADMIN_PASSWORD}).status_code == 403
    assert shared.post("/api/auth/verify-email", json={"code": "12345678"}).status_code == 403
    assert shared.post("/api/auth/resend-verification").status_code == 403
    assert shared.post("/api/auth/demo").status_code == 403
    assert sign_in(shared, "admin", DEMO_PASSWORD).status_code == 401


def test_personal_session_cannot_enter_shared_mode(client, monkeypatch):
    register_user(client)
    monkeypatch.setenv("AUTH_MODE", "shared")
    assert client.get("/api/auth/me").status_code == 401
    assert sign_in(client, "user@example.com", "correct-horse-battery").status_code == 401


def test_default_is_shared(client, monkeypatch):
    monkeypatch.delenv("AUTH_MODE", raising=False)
    assert client.get("/api/auth/config").json() == {"mode": "shared"}


def test_shared_passwords_can_be_short_and_named_admin_can_login(shared):
    configure_accounts(app.state.analysis_service, "short-admin", "short-demo")
    assert sign_in(shared, "adminteamscience", "short-admin").status_code == 200
    assert sign_in(shared, "demo", "short-demo").status_code == 200
    with pytest.raises(ValueError, match="required"):
        configure_accounts(app.state.analysis_service, "", "short-demo")
