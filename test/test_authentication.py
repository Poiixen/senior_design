"""Tests for user registration, login, logout and the current-user endpoint."""

from fastapi.testclient import TestClient

from backend.api.main import app
from backend.database import repository
from backend.database.connection import session_scope

CREDENTIALS = {"email": "user@example.com", "password": "correct-horse"}


def register(client, **overrides):
    return client.post("/api/auth/register", json={**CREDENTIALS, **overrides})


def test_register_succeeds(client):
    response = register(client)

    assert response.status_code == 201
    assert response.json() == {"id": 1, "email": "user@example.com"}


def test_register_rejects_duplicate_email_in_any_case(client):
    register(client)

    response = register(client, email="USER@example.com")

    assert response.status_code == 409


def test_register_validates_input(client):
    assert register(client, email="").status_code == 400
    assert register(client, email="not-an-email").status_code == 400
    assert register(client, password="").status_code == 400
    assert register(client, password="short").status_code == 400


def test_password_is_stored_as_hash(client, api_engine):
    register(client)

    with session_scope(api_engine) as session:
        user = repository.get_user_by_email(session, "user@example.com")

    assert user.password_hash != CREDENTIALS["password"]
    assert CREDENTIALS["password"] not in user.password_hash
    assert user.password_hash.startswith("$argon2")


def test_login_succeeds(client):
    register(client)
    client.post("/api/auth/logout")

    response = client.post("/api/auth/login", json=CREDENTIALS)

    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"
    assert client.get("/api/auth/me").status_code == 200


def test_wrong_password_and_unknown_account_get_the_same_failure(client):
    register(client)
    client.post("/api/auth/logout")

    wrong_password = client.post(
        "/api/auth/login", json={**CREDENTIALS, "password": "wrong-password"}
    )
    unknown_account = client.post(
        "/api/auth/login", json={**CREDENTIALS, "email": "nobody@example.com"}
    )

    assert wrong_password.status_code == 401
    assert unknown_account.status_code == 401
    assert wrong_password.json() == unknown_account.json()
    assert client.get("/api/auth/me").status_code == 401


def test_me_works_when_authenticated(client):
    register(client)

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json() == {"id": 1, "email": "user@example.com"}


def test_me_rejected_when_unauthenticated(client):
    assert client.get("/api/auth/me").status_code == 401


def test_logout_removes_authentication(client):
    register(client)

    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_login_survives_a_page_refresh(client):
    register(client)

    # A refresh is a new request that carries only the stored cookie.
    refreshed = TestClient(app, cookies=client.cookies)

    assert refreshed.get("/api/auth/me").json()["email"] == "user@example.com"


def test_frontend_origin_may_send_credentials(client):
    response = client.options(
        "/api/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_session_cookie_is_http_only(client):
    response = register(client)

    assert "httponly" in response.headers["set-cookie"].lower()


def test_password_hash_is_never_returned(client):
    responses = [
        register(client),
        client.post("/api/auth/login", json=CREDENTIALS),
        client.get("/api/auth/me"),
    ]

    for response in responses:
        assert "password" not in response.text
        assert "argon2" not in response.text
