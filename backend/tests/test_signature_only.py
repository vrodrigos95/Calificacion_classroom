"""Modo «solo revisar firma»: con firma = 100; sin firma = 90 con comentario (sin Claude)."""

from app.api.marks import verifier_factory
from app.main import app
from app.marks.verifier import LocalVerifier
from tests.test_batch_panel import _prepare, _thirty
from tests.test_grading_api import BASE, FakeClaude


def _statuses(client):
    return client.get(f"{BASE}/download").json()["submissions"]


def test_signed_100_unsigned_90_with_comment_without_claude(client, monkeypatch):
    files, subs = _thirty()
    fake = FakeClaude({})
    _prepare(client, monkeypatch, files, subs, fake)
    r = client.put(f"{BASE}/settings", json={"grading_mode": "solo_firma"}).json()
    assert r["unsigned_score"] == 90 and r["unsigned_comment"] == "La actividad tiene que estar firmada"

    client.post(f"{BASE}/process")
    st = _statuses(client)
    assert fake.calls == []  # no usa Claude ni necesita clave de respuestas
    signed = [st[f"s{i:02d}"] for i in range(1, 11)]
    unsigned = [st[f"s{i:02d}"] for i in range(11, 29)]
    assert all(d["panel_status"] == "con_marca" and d["final_score"] == 100 and d["final_comment"] == "" for d in signed)
    assert all(d["panel_status"] == "sin_firma" and d["final_score"] == 90 for d in unsigned)
    assert all(d["final_comment"] == "La actividad tiene que estar firmada" for d in unsigned)
    assert st["s29"]["panel_status"] == "error" and st["s30"]["panel_status"] == "sin_entrega"


def test_score_and_comment_are_configurable_and_apply_immediately(client, monkeypatch):
    files, subs = _thirty()
    _prepare(client, monkeypatch, files, subs, FakeClaude({}))
    client.put(f"{BASE}/settings", json={"grading_mode": "solo_firma"})
    client.post(f"{BASE}/process")
    client.put(f"{BASE}/settings", json={"unsigned_score": 80, "unsigned_comment": "Falta la firma del profesor."})
    d = _statuses(client)["s11"]
    assert d["final_score"] == 80 and d["final_comment"] == "Falta la firma del profesor."
    assert client.put(f"{BASE}/settings", json={"unsigned_score": 101}).status_code == 422


def test_local_mode_doubtful_needs_decision_before_any_score(client, monkeypatch):
    files, subs = _thirty()
    _prepare(client, monkeypatch, files, subs, FakeClaude({}))
    app.dependency_overrides[verifier_factory] = lambda: LocalVerifier  # sin clave de API
    client.put(f"{BASE}/settings", json={"grading_mode": "solo_firma"})
    client.post(f"{BASE}/process")
    d = _statuses(client)["s01"]
    assert d["panel_status"] == "revisar_a_mano" and d["final_score"] is None  # nunca 100 ni 90 sin decidir

    client.put(f"{BASE}/submissions/s01/mark-decision", json={"confirmed": True})
    assert _statuses(client)["s01"]["final_score"] == 100
    client.put(f"{BASE}/submissions/s01/mark-decision", json={"confirmed": False})
    d = _statuses(client)["s01"]
    assert d["panel_status"] == "sin_firma" and d["final_score"] == 90 and d["panel_note"] == "Rechazaste la marca"

    client.post(f"{BASE}/marks/confirm-all")
    st = _statuses(client)
    assert all(st[f"s{i:02d}"]["final_score"] == 100 for i in range(2, 11))


def test_solo_firma_forces_mark_search_on(client, monkeypatch):
    files, subs = _thirty()
    _prepare(client, monkeypatch, files, subs, FakeClaude({}))
    client.put(f"{BASE}/settings", json={"mark_module_enabled": False})
    r = client.put(f"{BASE}/settings", json={"grading_mode": "solo_firma"}).json()
    assert r["mark_module_enabled"] is True
