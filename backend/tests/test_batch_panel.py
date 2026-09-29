"""Etapa 5: procesamiento por lote y panel."""

from app.api.deps import classroom_reader
from app.api.downloads import file_source_factory
from app.api.grading import claude_factory
from app.api.marks import verifier_factory
from app.main import app
from tests.helpers import jpeg_bytes
from tests.test_auth_api import _login, _result
from tests.test_grading_api import BASE, GRADING_75, KEY, FakeClaude
from tests.test_marks import FakeVerifier, page_with, png, signature
from tests.test_pipeline import FakeSource, _sub, reader

SIGNED = jpeg_bytes(page_with([(950, 80)]))
UNSIGNED = jpeg_bytes(page_with([]))


def _thirty():
    files, subs = {}, []
    for i in range(1, 31):
        sid = f"s{i:02d}"
        if i == 30:
            subs.append(_sub(sid, "u1", "CREATED"))  # sin entrega
            continue
        fid = f"f{i}"
        if i == 29:
            files[fid] = ("application/pdf", b"%PDF-1.4 roto")
        else:
            files[fid] = ("image/jpeg", SIGNED if i <= 10 else UNSIGNED)
        subs.append(_sub(sid, "u1", "TURNED_IN", [fid]))
    return files, subs


class CountingClaude(FakeClaude):
    def __init__(self):
        super().__init__({})

    def structured(self, system, content, output, *, purpose, max_tokens=16000):
        self.responses.setdefault(output.__name__, []).append(GRADING_75)
        return super().structured(system, content, output, purpose=purpose, max_tokens=max_tokens)


def _prepare(client, monkeypatch, files, subs, fake):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "anthropic_api_key", "sk-test")
    _login(client, monkeypatch, _result())
    app.dependency_overrides[classroom_reader] = lambda: reader(subs)
    app.dependency_overrides[file_source_factory] = lambda: (lambda: FakeSource(files))
    app.dependency_overrides[verifier_factory] = lambda: (lambda: FakeVerifier(0.95))
    app.dependency_overrides[claude_factory] = lambda: (lambda: fake)
    client.post("/api/marks", data={"name": "Firma"}, files=[("files", ("f.png", png(signature()), "image/png"))])


def test_thirty_submissions_in_one_click(client, monkeypatch):
    files, subs = _thirty()
    fake = CountingClaude()
    _prepare(client, monkeypatch, files, subs, fake)
    client.put(f"{BASE}/key", json={"exercises": KEY})
    client.post(f"{BASE}/key/validate")

    # Un solo clic; el docente no hace nada más hasta ver el panel.
    assert client.post(f"{BASE}/process").json() == {"started": True}
    st = client.get(f"{BASE}/download").json()
    assert st["batch_phase"] == "listo" and not st["batch_running"]
    subs_out = st["submissions"]
    by_status: dict[str, list[str]] = {}
    for sid, d in subs_out.items():
        by_status.setdefault(d["panel_status"], []).append(sid)

    assert len(by_status["con_marca"]) == 10
    assert len(by_status["revisada"]) == 18
    assert by_status["error"] == ["s29"] and by_status["sin_entrega"] == ["s30"]
    assert all(subs_out[s]["final_score"] == 100 for s in by_status["con_marca"])
    assert all(subs_out[s]["final_score"] == 75 for s in by_status["revisada"])
    assert subs_out["s11"]["final_comment"].startswith("Ejercicio 3:")
    # Las firmadas no llamaron al modelo.
    assert len(fake.calls) == 18

    # Volver a procesar no recalifica lo que ya está.
    client.post(f"{BASE}/process")
    assert len(fake.calls) == 18

    # Si cambia la clave, al volver a procesar se recalifican solo las que usaron la clave vieja.
    client.put(f"{BASE}/key", json={"exercises": KEY})
    assert client.get(f"{BASE}/download").json()["submissions"]["s11"]["panel_status"] == "pendiente"
    client.post(f"{BASE}/key/validate")
    client.post(f"{BASE}/process")
    assert len(fake.calls) == 36


def test_without_validated_key_only_signed_are_scored(client, monkeypatch):
    files, subs = _thirty()
    fake = CountingClaude()
    _prepare(client, monkeypatch, files, subs, fake)
    client.post(f"{BASE}/process")
    st = client.get(f"{BASE}/download").json()
    statuses = [d["panel_status"] for d in st["submissions"].values()]
    assert statuses.count("con_marca") == 10 and statuses.count("pendiente") == 18
    assert "valides la clave" in st["batch_note"]
    assert fake.calls == []


def test_teacher_review_edits_and_captured(client, monkeypatch):
    files, subs = _thirty()
    _prepare(client, monkeypatch, files, subs, CountingClaude())
    client.put(f"{BASE}/key", json={"exercises": KEY})
    client.post(f"{BASE}/key/validate")
    client.post(f"{BASE}/process")

    url = f"{BASE}/submissions/s11/review"
    client.patch(url, json={"score_override": 80, "comment_override": "Ejercicio 3: revisa la conversión a porcentaje."})
    client.patch(url, json={"captured": True})
    d = client.get(f"{BASE}/download").json()["submissions"]["s11"]
    assert d["final_score"] == 80 and d["suggested_score"] == 75
    assert d["final_comment"].startswith("Ejercicio 3: revisa") and d["captured"]

    client.patch(url, json={"score_override": None, "comment_override": None})
    d = client.get(f"{BASE}/download").json()["submissions"]["s11"]
    assert d["final_score"] == 75 and d["captured"]  # null borra el ajuste; lo demás se queda
    assert client.patch(url, json={"score_override": 120}).status_code == 422

    # Si el alumno vuelve a entregar, hay que capturar de nuevo.
    subs[10] = _sub("s11", "u1", "TURNED_IN", ["nuevo"])
    files["nuevo"] = ("image/jpeg", UNSIGNED)
    client.post(f"{BASE}/process")
    d = client.get(f"{BASE}/download").json()["submissions"]["s11"]
    assert not d["captured"] and d["panel_status"] == "revisada"


def test_doubtful_mark_goes_to_manual_review_in_panel(client, monkeypatch):
    files, subs = _thirty()
    _prepare(client, monkeypatch, files, subs, CountingClaude())
    app.dependency_overrides[verifier_factory] = lambda: (lambda: FakeVerifier(0.7))
    client.put(f"{BASE}/key", json={"exercises": KEY})
    client.post(f"{BASE}/key/validate")
    client.post(f"{BASE}/process")
    d = client.get(f"{BASE}/download").json()["submissions"]["s01"]
    assert d["panel_status"] == "revisar_a_mano" and d["final_score"] == 75  # nunca 100 con marca dudosa
    client.put(f"{BASE}/submissions/s01/mark-decision", json={"confirmed": True})
    d = client.get(f"{BASE}/download").json()["submissions"]["s01"]
    assert d["panel_status"] == "con_marca" and d["final_score"] == 100
