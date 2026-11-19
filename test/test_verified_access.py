from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.api import auth
from backend.api.main import app
from backend.database.connection import session_scope, create_sqlite_engine, initialize_database
from backend.database import repository
from backend.models.account_security import VerificationChallenge, AccountVerification, LoginSession
from backend.services import account_security, auth_service
from conftest import register_user

CREDENTIALS = {"email": "verify@example.com", "password": "a-long-test-password"}
REAL_SEND_EMAIL = account_security.send_verification_email


def pending(client):
    response = client.post("/api/auth/register", json=CREDENTIALS)
    assert response.status_code == 201
    assert response.json() == {"verification_required": True}
    return app.state.test_outbox[CREDENTIALS["email"]]


def test_no_access_until_email_verified(client):
    code = pending(client)
    for path in ["/api/auth/me", "/api/reports", "/api/reports/1"]:
        assert client.get(path).status_code == 401
    assert client.post("/api/auth/verify-email", json={"code": code}).status_code == 200
    assert client.get("/api/reports").status_code == 200


def test_code_is_hashed_and_bound_to_requesting_browser(client, api_engine):
    code = pending(client)
    with session_scope(api_engine) as session:
        challenge = session.scalars(select(VerificationChallenge)).one()
        assert code not in challenge.code_hash
    other = TestClient(app)
    assert other.post("/api/auth/verify-email", json={"code": code}).status_code == 400
    assert client.post("/api/auth/verify-email", json={"code": code}).status_code == 200


def test_code_is_single_use_even_with_copied_pending_cookie(client):
    code = pending(client)
    copied = TestClient(app, cookies=client.cookies)
    assert client.post("/api/auth/verify-email", json={"code": code}).status_code == 200
    assert copied.post("/api/auth/verify-email", json={"code": code}).status_code == 400


def test_concurrent_code_consumption_only_succeeds_once(client):
    code = pending(client)
    cookie = client.cookies.get("session")
    # Do not enter app lifespan for concurrent clients sharing the fixture engine.
    def consume_without_lifespan(_):
        browser = TestClient(app, cookies={"session": cookie})
        return browser.post("/api/auth/verify-email", json={"code": code}).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(consume_without_lifespan, range(2))) == [200, 400]


def test_five_wrong_codes_lock_challenge(client):
    code = pending(client)
    wrong = "00000000" if code != "00000000" else "11111111"
    for _ in range(5):
        assert client.post("/api/auth/verify-email", json={"code": wrong}).status_code == 400
    assert client.post("/api/auth/verify-email", json={"code": code}).status_code == 400
    assert client.get("/api/reports").status_code == 401


def test_expired_codes_and_resend_rotation(client, monkeypatch):
    monkeypatch.setattr(auth, "time", lambda: 1000)
    old = pending(client)
    monkeypatch.setattr(auth, "time", lambda: 1600)
    assert client.post("/api/auth/verify-email", json={"code": old}).status_code == 400
    assert client.post("/api/auth/resend-verification").status_code == 200
    new = app.state.test_outbox[CREDENTIALS["email"]]
    assert client.post("/api/auth/verify-email", json={"code": new}).status_code == 200


def test_resend_invalidates_old_browser_challenge(client):
    code = pending(client)
    old_browser = TestClient(app, cookies=client.cookies)
    assert client.post("/api/auth/resend-verification").status_code == 200
    assert old_browser.post("/api/auth/verify-email", json={"code": code}).status_code == 400
    assert client.post("/api/auth/resend-verification").status_code == 200
    assert client.post("/api/auth/resend-verification").status_code == 429


def test_delivery_failure_never_grants_access_and_can_retry(client, monkeypatch):
    def fail(*args):
        raise RuntimeError("SECRET SMTP DIAGNOSTIC")
    monkeypatch.setattr(account_security, "send_verification_email", fail)
    response = client.post("/api/auth/register", json=CREDENTIALS)
    assert response.status_code == 503
    assert "SECRET" not in response.text
    assert client.get("/api/reports").status_code == 401
    outbox = {}
    monkeypatch.setattr(account_security, "send_verification_email", lambda email, code: outbox.update({email: code}))
    assert client.post("/api/auth/resend-verification").status_code == 200
    assert client.post("/api/auth/verify-email", json={"code": outbox[CREDENTIALS["email"]]}).status_code == 200


def test_existing_account_must_verify_without_losing_data(client, api_engine):
    with session_scope(api_engine) as session:
        user = repository.create_user(session, email=CREDENTIALS["email"], password_hash=auth_service.hash_password("old-password"))
    response = client.post("/api/auth/login", json={**CREDENTIALS, "password": "old-password"})
    assert response.json() == {"verification_required": True}
    assert client.get("/api/reports").status_code == 401
    assert client.post("/api/auth/verify-email", json={"code": app.state.test_outbox[user.email]}).json()["id"] == user.id


def test_logout_revokes_copied_session_cookie(auth_client):
    copied = TestClient(app, cookies=auth_client.cookies)
    assert copied.get("/api/auth/me").status_code == 200
    assert auth_client.post("/api/auth/logout").status_code == 200
    assert copied.get("/api/auth/me").status_code == 401


def test_verification_revocation_blocks_existing_session(auth_client, api_engine):
    with session_scope(api_engine) as session:
        session.get(AccountVerification, 1).verified_at = None
    assert auth_client.get("/api/reports").status_code == 401


def test_absolute_session_expiry(auth_client, api_engine):
    with session_scope(api_engine) as session:
        session.scalars(select(LoginSession)).one().absolute_expires_at = 0
    assert auth_client.get("/api/auth/me").status_code == 401


def test_auth_rate_limit_applies_across_clients(client):
    for _ in range(10):
        assert client.post("/api/auth/login", json=CREDENTIALS).status_code == 401
    other = TestClient(app)
    response = other.post("/api/auth/login", json=CREDENTIALS)
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


def test_demo_and_public_api_docs_cannot_bypass_gate(client, monkeypatch):
    monkeypatch.setenv("SHOWCASE_ENABLED", "true")
    assert client.post("/api/auth/demo").status_code == 403
    for path in ["/docs", "/redoc", "/openapi.json"]:
        assert client.get(path).status_code == 404


def test_schema_upgrade_adds_security_tables_without_changing_users(tmp_path):
    engine = create_sqlite_engine(tmp_path / "old.sqlite")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, password_hash TEXT, created_at DATETIME)")
        connection.exec_driver_sql("INSERT INTO users VALUES (1, 'old@example.com', 'hash', '2026-01-01')")
    initialize_database(engine)
    initialize_database(engine)
    with session_scope(engine) as session:
        assert repository.get_user(session, 1).email == "old@example.com"
        assert session.get(AccountVerification, 1) is None
    engine.dispose()


@pytest.mark.parametrize("email", ["first,second@example.com", "x@example.com\r\nBcc: attacker@example.com", "x <other@example.com>"])
def test_registration_rejects_multiple_recipients_and_header_injection(client, email):
    assert client.post("/api/auth/register", json={**CREDENTIALS, "email": email}).status_code == 400


def test_smtp_delivery_uses_tls_before_authentication(monkeypatch):
    events = []
    class SMTP:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("smtp.example.com", 587, 15)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def starttls(self, context):
            assert context.check_hostname
            events.append("tls")
        def login(self, user, password):
            assert events == ["tls"]
            events.append("login")
        def send_message(self, message):
            assert message["To"] == CREDENTIALS["email"]
            assert "12345678" in message.get_content()
            events.append("send")
    for name, value in {"SMTP_HOST": "smtp.example.com", "SMTP_PORT": "587", "SMTP_SECURITY": "starttls",
                        "SMTP_FROM": "noreply@example.com", "SMTP_USERNAME": "test", "SMTP_PASSWORD": "test"}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(account_security.smtplib, "SMTP", SMTP)
    REAL_SEND_EMAIL(CREDENTIALS["email"], "12345678")
    assert events == ["tls", "login", "send"]


def test_missing_smtp_configuration_fails_closed(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    with pytest.raises(RuntimeError, match="not configured"):
        REAL_SEND_EMAIL(CREDENTIALS["email"], "12345678")
