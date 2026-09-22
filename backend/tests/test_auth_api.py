from urllib.parse import parse_qs, urlparse

import pytest

from app.api.deps import classroom_reader
from app.auth import google_oauth
from app.classroom.client import ClassroomReader
from app.config import GOOGLE_SCOPES
from app.db.models import OAuthToken
from app.db.session import SessionLocal
from app.main import app
from tests.test_classroom_reader import make_service


def _result(scopes=None):
    return google_oauth.OAuthResult(
        google_sub="sub-123",
        email="docente@example.com",
        name="Docente Prueba",
        refresh_token="1//refresh-secreto",
        granted_scopes=set(scopes if scopes is not None else GOOGLE_SCOPES),
    )


def _login(client, monkeypatch, result):
    resp = client.get("/api/auth/login")
    state = parse_qs(urlparse(resp.headers["location"]).query)["state"][0]
    monkeypatch.setattr(google_oauth, "finish_authorization", lambda code, st, v: result)
    return client.get(f"/api/auth/callback?code=abc&state={state}")


def test_login_redirects_to_google_with_exact_scopes_offline_and_pkce(client):
    resp = client.get("/api/auth/login")
    assert resp.status_code == 303
    url = urlparse(resp.headers["location"])
    assert url.netloc == "accounts.google.com"
    q = parse_qs(url.query)
    assert set(q["scope"][0].split()) == set(GOOGLE_SCOPES)
    assert q["access_type"] == ["offline"]
    assert q["prompt"] == ["consent"]
    assert q["code_challenge_method"] == ["S256"]
    assert q["redirect_uri"] == ["http://localhost:5173/api/auth/callback"]


def test_callback_rejects_bad_state(client, monkeypatch):
    client.get("/api/auth/login")
    monkeypatch.setattr(
        google_oauth, "finish_authorization", lambda *a: pytest.fail("no debe llamarse")
    )
    resp = client.get("/api/auth/callback?code=abc&state=otro")
    assert "error=estado_invalido" in resp.headers["location"]


def test_callback_reports_missing_scopes(client, monkeypatch):
    partial = [s for s in GOOGLE_SCOPES if "drive" not in s]
    resp = _login(client, monkeypatch, _result(partial))
    loc = resp.headers["location"]
    assert "error=permisos" in loc and "drive.readonly" in loc
    assert client.get("/api/auth/me").status_code == 401


def test_successful_login_stores_encrypted_token_and_opens_session(client, monkeypatch):
    resp = _login(client, monkeypatch, _result())
    assert resp.headers["location"] == "http://localhost:5173/"

    me = client.get("/api/auth/me").json()
    assert me["email"] == "docente@example.com"

    with SessionLocal() as db:
        tok = db.query(OAuthToken).one()
        assert b"refresh-secreto" not in tok.refresh_token_enc
        creds = google_oauth.credentials_for(db, me["id"])
        assert creds.refresh_token == "1//refresh-secreto"

    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401


def test_courses_require_login(client):
    assert client.get("/api/courses").status_code == 401


def test_submissions_endpoint(client, monkeypatch):
    _login(client, monkeypatch, _result())
    app.dependency_overrides[classroom_reader] = lambda: ClassroomReader(make_service())

    assert client.get("/api/courses").json()[0]["id"] == "c1"
    assert [w["id"] for w in client.get("/api/courses/c1/coursework").json()] == ["w1", "w2"]

    data = client.get("/api/courses/c1/coursework/w1/submissions").json()
    assert data["coursework"]["title"] == "Probabilidad"
    assert data["summary"] == {"total": 5, "entregadas": 2, "sin_archivos": 1, "sin_entrega": 2}

    assert client.get("/api/courses/c1/coursework/nope/submissions").status_code == 404


def test_scope_aliases_are_normalized():
    granted = google_oauth.normalize_scopes("openid email profile " + " ".join(GOOGLE_SCOPES[3:]))
    assert google_oauth.missing_scopes(granted) == []


def test_write_scope_covers_readonly():
    granted = set(GOOGLE_SCOPES) - {"https://www.googleapis.com/auth/classroom.coursework.students.readonly"}
    granted.add("https://www.googleapis.com/auth/classroom.coursework.students")
    assert google_oauth.missing_scopes(granted) == []
