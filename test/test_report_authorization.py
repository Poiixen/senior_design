"""Reports belong to the user who uploaded them."""

from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from backend.api.main import app
from backend.database import repository
from backend.database.connection import (
    create_sqlite_engine,
    initialize_database,
    session_scope,
)
from conftest import register_user

CSV = "name,age\nAlice,20\nBob,30\n"


def upload(client, filename="data.csv"):
    return client.post(
        "/api/analyze", files={"file": (filename, CSV, "text/csv")}
    )


def make_user_client(email):
    """A separate browser: its own cookie jar, same app and database."""
    client = TestClient(app)
    register_user(client, email=email)
    return client


def test_user_sees_own_report_in_list_and_by_id(client):
    register_user(client, email="a@example.com")
    analysis_id = upload(client).json()["analysis_id"]

    listed = client.get("/api/reports").json()["reports"]

    assert [r["analysis_id"] for r in listed] == [analysis_id]
    assert client.get(f"/api/reports/{analysis_id}").status_code == 200


def test_other_user_cannot_see_or_fetch_the_report(client):
    register_user(client, email="a@example.com")
    analysis_id = upload(client).json()["analysis_id"]
    user_b = make_user_client("b@example.com")

    assert user_b.get("/api/reports").json() == {"reports": []}
    response = user_b.get(f"/api/reports/{analysis_id}")
    assert response.status_code == 404
    assert response.json() == user_b.get("/api/reports/999999").json()

    # User A still has access.
    assert client.get(f"/api/reports/{analysis_id}").status_code == 200


def test_each_user_only_gets_their_own_reports(client):
    register_user(client, email="a@example.com")
    user_b = make_user_client("b@example.com")
    a_ids = [upload(client, f"a{i}.csv").json()["analysis_id"] for i in range(2)]
    b_ids = [upload(user_b, f"b{i}.csv").json()["analysis_id"] for i in range(3)]

    a_listed = [r["analysis_id"] for r in client.get("/api/reports").json()["reports"]]
    b_listed = [r["analysis_id"] for r in user_b.get("/api/reports").json()["reports"]]

    assert a_listed == sorted(a_ids, reverse=True)
    assert b_listed == sorted(b_ids, reverse=True)
    assert user_b.get(f"/api/reports/{a_ids[0]}").status_code == 404
    assert client.get(f"/api/reports/{b_ids[0]}").status_code == 404


def test_uploaded_dataset_is_owned_by_the_uploader(client, api_engine):
    user = register_user(client, email="a@example.com")
    upload(client)

    with session_scope(api_engine) as session:
        datasets = repository.list_datasets(session)

    assert [d.user_id for d in datasets] == [user["id"]]


def test_other_users_failed_analysis_is_not_revealed(client, api_engine):
    register_user(client, email="a@example.com")
    analysis_id = upload(client).json()["analysis_id"]
    with session_scope(api_engine) as session:
        session.execute(text("DELETE FROM analysis_reports"))
        session.execute(
            text(
                "UPDATE analyses SET status='failed' WHERE id=:id"
            ),
            {"id": analysis_id},
        )
    user_b = make_user_client("b@example.com")

    assert client.get(f"/api/reports/{analysis_id}").status_code == 409
    assert user_b.get(f"/api/reports/{analysis_id}").status_code == 404


def test_unauthenticated_requests_are_rejected(client):
    assert upload(client).status_code == 401
    assert client.get("/api/reports").status_code == 401
    assert client.get("/api/reports/1").status_code == 401
    assert client.get("/health").status_code == 200


def test_reports_without_an_owner_are_hidden(client, api_engine):
    with session_scope(api_engine) as session:
        dataset = repository.create_dataset(
            session, name="old", row_count=1, column_count=1
        )
        analysis = repository.create_analysis(session, dataset.id)
        repository.finish_analysis(session, analysis.id)
        repository.save_analysis_report(session, analysis.id, {"analysis_id": analysis.id})
    register_user(client, email="a@example.com")

    assert client.get("/api/reports").json() == {"reports": []}
    assert client.get(f"/api/reports/{analysis.id}").status_code == 404


def test_old_database_gains_owner_column(tmp_path):
    engine = create_sqlite_engine(tmp_path / "old.sqlite3")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE datasets (id INTEGER PRIMARY KEY, name TEXT, source TEXT, "
            "file_name TEXT, row_count INTEGER, column_count INTEGER, created_at DATETIME)"
        ))

    initialize_database(engine)
    initialize_database(engine)  # safe to run again

    columns = {c["name"] for c in inspect(engine).get_columns("datasets")}
    assert "user_id" in columns
    engine.dispose()
