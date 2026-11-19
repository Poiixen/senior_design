from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from backend.api.security import session_secret
from backend.ingestion import dataset_loader


@pytest.mark.parametrize("origin", ["https://evil.example", "null", "http://localhost:5173.evil.example"])
@pytest.mark.parametrize("path", ["/api/auth/login", "/api/auth/logout", "/api/analyze"])
def test_untrusted_origins_cannot_mutate(client, origin, path):
    response = client.post(path, headers={"Origin": origin})
    assert response.status_code == 403


def test_cross_site_logout_does_not_destroy_session(auth_client):
    assert auth_client.post("/api/auth/logout", headers={"Origin": "https://evil.example"}).status_code == 403
    assert auth_client.get("/api/auth/me").status_code == 200


def test_trusted_frontend_can_write(client):
    assert client.post("/api/auth/logout", headers={"Origin": "http://localhost:5173"}).status_code == 200


def test_browser_without_origin_fails_closed(client):
    assert client.post("/api/auth/logout", headers={"Sec-Fetch-Site": "same-site"}).status_code == 403


def test_referer_fallback(client):
    assert client.post("/api/auth/logout", headers={"Referer": "https://evil.example/page"}).status_code == 403
    assert client.post("/api/auth/logout", headers={"Referer": "http://localhost:5173/dashboard"}).status_code == 200


@pytest.mark.parametrize("path", ["/api/auth/me", "/api/nonexistent"])
def test_private_responses_are_not_cached(client, path):
    response = client.get(path)
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


@pytest.mark.parametrize("secret", [None, "short", "replace-with-output-of-openssl-rand-hex-32"])
def test_secure_sessions_reject_unsafe_keys(secret):
    with pytest.raises(ValueError, match="SECRET_KEY"):
        session_secret(secret, True)


def test_session_configuration():
    assert len(session_secret(None, False)) >= 32
    assert session_secret("a" * 64, True) == "a" * 64


@pytest.mark.parametrize("limit", ["MAX_XLSX_EXPANDED_BYTES", "MAX_XLSX_MEMBERS"])
def test_compressed_workbook_limits_before_pandas(tmp_path, monkeypatch, limit):
    path = tmp_path / "bomb.xlsx"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", "x" * 10000)
        archive.writestr("xl/workbook.xml", "x")
    monkeypatch.setattr(dataset_loader, limit, 1)
    def unexpected_read(*args, **kwargs):
        pytest.fail("Oversized archives must be rejected before pandas reads them")
    monkeypatch.setattr(dataset_loader.pd, "read_excel", unexpected_read)
    with pytest.raises(dataset_loader.DatasetLoadError, match="expanded size"):
        dataset_loader.load_dataset(str(path), path.name)
