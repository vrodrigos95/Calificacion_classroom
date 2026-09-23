from app.api.deps import classroom_reader
from app.api.downloads import file_source_factory
from app.main import app
from tests.test_auth_api import _login, _result
from tests.test_pipeline import FILES, SUBS, FakeSource, reader


def test_download_flow_and_page_access(client, monkeypatch):
    _login(client, monkeypatch, _result())
    app.dependency_overrides[classroom_reader] = lambda: reader(SUBS)
    app.dependency_overrides[file_source_factory] = lambda: (lambda: FakeSource(FILES))

    # Antes de descargar no hay estado.
    assert client.get("/api/courses/c1/coursework/w1/download").json()["submissions"] == {}

    # POST sincroniza y encola; TestClient ejecuta la tarea en segundo plano al terminar.
    resp = client.post("/api/courses/c1/coursework/w1/download")
    assert resp.status_code == 200
    assert resp.json()["counts"]["pendiente"] == 4

    status = client.get("/api/courses/c1/coursework/w1/download").json()
    assert status["running"] is False
    assert status["counts"] == {"lista": 1, "error": 4, "sin_entrega": 1}
    s1 = status["submissions"]["s1"]
    assert s1["status"] == "lista" and len(s1["pages"]) == 3
    assert status["submissions"]["s2"]["error"].startswith("PDF dañado")

    img = client.get(f"/api/pages/{s1['pages'][0]['id']}")
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert img.content[:2] == b"\xff\xd8"


def test_pages_are_private_to_their_teacher(client, monkeypatch):
    _login(client, monkeypatch, _result())
    app.dependency_overrides[classroom_reader] = lambda: reader(SUBS[:1])
    app.dependency_overrides[file_source_factory] = lambda: (lambda: FakeSource(FILES))
    client.post("/api/courses/c1/coursework/w1/download")
    page_id = client.get("/api/courses/c1/coursework/w1/download").json()["submissions"]["s1"]["pages"][0]["id"]

    # Otro docente no puede ver la imagen.
    otro = _result()
    otro.google_sub, otro.email = "otro-sub", "otro@example.com"
    client.post("/api/auth/logout")
    _login(client, monkeypatch, otro)
    assert client.get(f"/api/pages/{page_id}").status_code == 404

    client.post("/api/auth/logout")
    assert client.get(f"/api/pages/{page_id}").status_code == 401
