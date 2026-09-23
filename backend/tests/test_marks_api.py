from app.api.deps import classroom_reader
from app.api.downloads import file_source_factory
from app.api.marks import verifier_factory
from app.main import app
from tests.helpers import jpeg_bytes
from tests.test_auth_api import _login, _result
from tests.test_marks import FakeVerifier, page_with, png, signature
from tests.test_pipeline import FakeSource, _sub, reader

FILES = {
    "firmada": ("image/jpeg", jpeg_bytes(page_with([(950, 80)]))),
    "sin_firma": ("image/jpeg", jpeg_bytes(page_with([]))),
}
SUBS = [_sub("s1", "u1", "TURNED_IN", ["firmada"]), _sub("s2", "u2", "TURNED_IN", ["sin_firma"])]


def _prepare(client, monkeypatch, confidence=0.95):
    _login(client, monkeypatch, _result())
    app.dependency_overrides[classroom_reader] = lambda: reader(SUBS)
    app.dependency_overrides[file_source_factory] = lambda: (lambda: FakeSource(FILES))
    app.dependency_overrides[verifier_factory] = lambda: (lambda: FakeVerifier(confidence))


def _create_mark(client, **extra):
    data = {"name": "Firma verde", "meaning": "correcta", "zone": "primera", **extra}
    return client.post("/api/marks", data=data, files=[("files", ("f.png", png(signature()), "image/png"))])


def test_mark_crud(client, monkeypatch):
    _prepare(client, monkeypatch)
    r = _create_mark(client)
    assert r.status_code == 200, r.text
    mark = r.json()
    assert mark["colored"] and len(mark["references"]) == 1
    assert client.get(mark["references"][0]["url"]).headers["content-type"] == "image/png"

    cfg = client.get("/api/marks").json()
    assert cfg["verifier"] == "local" and [m["id"] for m in cfg["marks"]] == [mark["id"]]

    r = client.patch(f"/api/marks/{mark['id']}", json={"zone": "cualquiera", "meaning": "informativa"})
    assert r.json()["zone"] == "cualquiera" and r.json()["meaning"] == "informativa"
    assert client.patch(f"/api/marks/{mark['id']}", json={"zone": "otra"}).status_code == 422

    bad = client.post("/api/marks", data={"name": "x"}, files=[("files", ("a.png", b"no es imagen", "image/png"))])
    assert bad.status_code == 400 and "no se pudo abrir" in bad.json()["detail"]

    assert client.delete(f"/api/marks/{mark['id']}").status_code == 204
    assert client.get("/api/marks").json()["marks"] == []


def test_detect_flow_with_decisions(client, monkeypatch):
    _prepare(client, monkeypatch, confidence=0.7)  # coincidencia dudosa
    _create_mark(client)
    base = "/api/courses/c1/coursework/w1"
    assert client.post(f"{base}/marks/detect").status_code == 409  # sin descargar aún
    client.post(f"{base}/download")
    assert client.post(f"{base}/marks/detect").json() == {"started": True}

    st = client.get(f"{base}/download").json()
    s1, s2 = st["submissions"]["s1"], st["submissions"]["s2"]
    assert s1["mark_status"] == "dudosa" and s1["suggested_score"] is None  # nunca 100 si es dudosa
    assert s2["mark_status"] == "sin_marca" and s2["detections"] == []
    det = s1["detections"][0]
    assert det["verdict"] == "dudosa" and det["mark_name"] == "Firma verde"
    crop = client.get(f"/api/detections/{det['id']}/crop")
    assert crop.status_code == 200 and crop.content[:2] == b"\xff\xd8"

    # El docente confirma: ahora sí 100.
    client.put(f"{base}/submissions/s1/mark-decision", json={"confirmed": True})
    s1 = client.get(f"{base}/download").json()["submissions"]["s1"]
    assert s1["mark_status"] == "con_marca" and s1["suggested_score"] == 100
    # No se puede confirmar una marca que no tiene recorte.
    assert client.put(f"{base}/submissions/s2/mark-decision", json={"confirmed": True}).status_code == 409
    # Deshacer.
    client.put(f"{base}/submissions/s1/mark-decision", json={"confirmed": None})
    assert client.post(f"{base}/marks/confirm-all").json() == {"confirmed": 1}


def test_clear_mark_gets_100_and_toggle_disables_module(client, monkeypatch):
    _prepare(client, monkeypatch, confidence=0.95)
    _create_mark(client)
    base = "/api/courses/c1/coursework/w1"
    client.post(f"{base}/download")
    client.post(f"{base}/marks/detect")
    s1 = client.get(f"{base}/download").json()["submissions"]["s1"]
    assert s1["mark_status"] == "con_marca" and s1["suggested_score"] == 100

    assert client.put(f"{base}/settings", json={"mark_module_enabled": False}).json() == {"mark_module_enabled": False}
    client.post(f"{base}/marks/detect")
    st = client.get(f"{base}/download").json()
    assert st["mark_module_enabled"] is False
    assert st["submissions"]["s1"]["mark_status"] == "desactivado"
    assert st["submissions"]["s1"]["suggested_score"] is None


def test_crops_and_marks_are_private(client, monkeypatch):
    _prepare(client, monkeypatch)
    mark = _create_mark(client).json()
    base = "/api/courses/c1/coursework/w1"
    client.post(f"{base}/download")
    client.post(f"{base}/marks/detect")
    det_id = client.get(f"{base}/download").json()["submissions"]["s1"]["detections"][0]["id"]

    otro = _result()
    otro.google_sub = "otro"
    client.post("/api/auth/logout")
    _login(client, monkeypatch, otro)
    assert client.get(f"/api/detections/{det_id}/crop").status_code == 404
    assert client.get(mark["references"][0]["url"]).status_code == 404
    assert client.delete(f"/api/marks/{mark['id']}").status_code == 404
