import pytest

from app.api.deps import classroom_reader
from app.api.downloads import file_source_factory
from app.api.grading import claude_factory
from app.api.marks import verifier_factory
from app.config import get_settings
from app.grading.schemas import GradingOut, KeyModelOut, StatementOut
from app.main import app
from app.vision.claude_client import VisionError
from tests.helpers import jpeg_bytes, pdf_bytes
from tests.test_auth_api import _login, _result
from tests.test_marks import FakeVerifier, page_with, png, signature
from tests.test_pipeline import FakeSource, _sub, reader
from tests.test_scoring import ex

BASE = "/api/courses/c1/coursework/w1"

FILES = {
    "firmada": ("image/jpeg", jpeg_bytes(page_with([(950, 80)]))),
    "hoja1": ("image/jpeg", jpeg_bytes(page_with([]))),
    "hoja2": ("image/jpeg", jpeg_bytes(page_with([]))),
    "material": ("application/pdf", pdf_bytes(1)),
}
SUBS = [
    _sub("s1", "u1", "TURNED_IN", ["firmada"]),
    _sub("s2", "u2", "TURNED_IN", ["hoja1"]),
    _sub("s3", "u3", "TURNED_IN", ["hoja2"]),
]
KEY = [
    {"numero": "1", "enunciado": "dado > 4", "respuesta_final": "33%"},
    {"numero": "2", "enunciado": "rey o as", "respuesta_final": "15.38%"},
    {"numero": "3", "enunciado": "natación y tenis", "respuesta_final": "40%"},
    {"numero": "4", "enunciado": "fútbol o básquet", "respuesta_final": "P(A ∪ B) = 70%", "criterios_notacion": ["usar ∪"]},
]


class FakeClaude:
    """Imita ClaudeClient.structured: responde según el tipo de salida pedido."""

    model = "claude-opus-5"

    def __init__(self, responses: dict):
        self.responses = {k: list(v) for k, v in responses.items()}
        self.calls = []

    def structured(self, system, content, output, *, purpose, max_tokens=16000):
        self.calls.append((output.__name__, purpose, content))
        item = self.responses[output.__name__].pop(0)
        if isinstance(item, Exception):
            raise item
        from app.vision.claude_client import Usage

        return output.model_validate(item), Usage(1500, 300)


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "sk-test")


def _prepare(client, monkeypatch, fake=None, description="", materials=()):
    _login(client, monkeypatch, _result())
    cw = {"id": "w1", "title": "Probabilidad", "description": description,
          "materials": [{"driveFile": {"driveFile": {"id": m, "title": m}}} for m in materials]}
    r = reader(SUBS)
    r.svc.coursework.pages_by_parent["c1"] = [{"courseWork": [cw]}]
    app.dependency_overrides[classroom_reader] = lambda: r
    app.dependency_overrides[file_source_factory] = lambda: (lambda: FakeSource(FILES))
    app.dependency_overrides[verifier_factory] = lambda: (lambda: FakeVerifier(0.95))
    fake = fake or FakeClaude({})
    app.dependency_overrides[claude_factory] = lambda: (lambda: fake)
    return fake


def _download(client):
    client.post(f"{BASE}/download")


def test_manual_key_must_be_validated_and_edits_unvalidate(client, monkeypatch):
    _prepare(client, monkeypatch)
    assert client.get(f"{BASE}/key").json()["state"] == "sin_clave"

    r = client.put(f"{BASE}/key", json={"exercises": KEY[:2] + [{"numero": "2", "respuesta_final": "x"}]})
    assert r.json()["state"] == "sin_validar"
    assert "repetidos" in client.post(f"{BASE}/key/validate").json()["detail"]

    client.put(f"{BASE}/key", json={"exercises": KEY[:1] + [{"numero": "2", "respuesta_final": " "}]})
    assert "Falta la respuesta del ejercicio 2" in client.post(f"{BASE}/key/validate").json()["detail"]

    client.put(f"{BASE}/key", json={"exercises": KEY})
    k = client.post(f"{BASE}/key/validate").json()
    assert k["state"] == "validada" and k["validated_at"]
    v = k["version"]

    k = client.put(f"{BASE}/key", json={"exercises": KEY[:3]}).json()
    assert k["state"] == "sin_validar" and k["version"] == v + 1


def test_model_features_need_api_key(client, monkeypatch):
    _prepare(client, monkeypatch)
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    r = client.post(f"{BASE}/key/solve")
    assert r.status_code == 409 and "ANTHROPIC_API_KEY" in r.json()["detail"]
    r = client.post(f"{BASE}/key/from-teacher", data={"text": "1) 33%"})
    assert r.status_code == 409


def test_key_from_teacher_upload(client, monkeypatch, with_key):
    fake = FakeClaude({"KeyModelOut": [{
        "ejercicios": [dict(k, procedimiento_clave="", criterios_notacion=[], confianza=0.95) for k in KEY[:3]]
        + [dict(KEY[3], procedimiento_clave="", confianza=0.5)],
        "observaciones": "",
    }]})
    _prepare(client, monkeypatch, fake)
    r = client.post(
        f"{BASE}/key/from-teacher",
        data={"text": "Clave: 1) 33% 2) 15.38% ..."},
        files=[("files", ("clave.png", png(signature()), "image/png"))],
    )
    assert r.status_code == 200, r.text
    k = client.get(f"{BASE}/key").json()
    assert k["state"] == "sin_validar" and len(k["exercises"]) == 4 and k["source"] == "docente"
    assert "ejercicios 4" in k["warning"]  # confianza baja: avisa
    _, _, content = fake.calls[0]
    assert sum(b["type"] == "image" for b in content) == 1


def test_solve_uses_classroom_statement_when_present(client, monkeypatch, with_key):
    fake = FakeClaude({
        "StatementOut": [{"enunciado_encontrado": True, "ejercicios": [{"numero": k["numero"], "enunciado": k["enunciado"]} for k in KEY], "observaciones": ""}],
        "KeyModelOut": [{"ejercicios": [dict(k, enunciado="", procedimiento_clave="", criterios_notacion=[], confianza=0.95) for k in KEY], "observaciones": ""}],
    })
    _prepare(client, monkeypatch, fake, description="Resuelve los 4 ejercicios", materials=["material"])
    client.post(f"{BASE}/key/solve")
    k = client.get(f"{BASE}/key").json()
    assert k["state"] == "sin_validar" and k["statement_source"] == "classroom"
    assert k["source"] == "resuelta_por_modelo"
    assert k["exercises"][0]["enunciado"] == "dado > 4"  # conserva el enunciado encontrado
    assert [c[0] for c in fake.calls] == ["StatementOut", "KeyModelOut"]


def test_solve_falls_back_to_student_sheets_and_warns_on_different_statements(client, monkeypatch, with_key):
    same = [{"numero": k["numero"], "enunciado": k["enunciado"]} for k in KEY]
    other = same[:3] + [{"numero": "4", "enunciado": "Calcula el área de un círculo de radio 3"}]
    fake = FakeClaude({
        "StatementOut": [
            {"enunciado_encontrado": False, "ejercicios": [], "observaciones": "solo instrucciones"},  # Classroom
            {"enunciado_encontrado": True, "ejercicios": same, "observaciones": ""},
            {"enunciado_encontrado": True, "ejercicios": same, "observaciones": ""},
            {"enunciado_encontrado": True, "ejercicios": other, "observaciones": ""},
        ],
        "KeyModelOut": [{"ejercicios": [dict(k, procedimiento_clave="", criterios_notacion=[], confianza=0.95) for k in KEY], "observaciones": ""}],
    })
    _prepare(client, monkeypatch, fake, description="Suban su tarea con mi firma")
    _download(client)
    client.post(f"{BASE}/key/solve")
    k = client.get(f"{BASE}/key").json()
    assert k["statement_source"] == "hojas_de_alumnos"
    assert "enunciados diferentes" in k["warning"] and "ejercicio 4 de la hoja 3" in k["warning"]
    assert k["state"] == "sin_validar"  # nunca se valida sola


def test_solve_without_statement_and_without_downloads_explains(client, monkeypatch, with_key):
    fake = FakeClaude({"StatementOut": [{"enunciado_encontrado": False, "ejercicios": [], "observaciones": ""}]})
    _prepare(client, monkeypatch, fake, description="Suban su tarea")
    client.post(f"{BASE}/key/solve")
    k = client.get(f"{BASE}/key").json()
    assert k["state"] == "error" and "Descarga las entregas" in k["job_error"]


def _validated_key_and_downloads(client):
    client.put(f"{BASE}/key", json={"exercises": KEY})
    client.post(f"{BASE}/key/validate")
    _download(client)


GRADING_75 = {
    "ejercicios": [ex("1"), ex("2"),
                   ex("3", "error_menor", comentario="tu procedimiento está bien, pero 0.4 equivale a 40%, no a 4%."),
                   ex("4", "error_menor", comentario="el resultado es correcto; 'o' es unión (∪), no intersección (∩).")],
    "ejercicios_no_encontrados": [],
    "enunciado_coincide_con_clave": True,
    "observaciones": "",
}


def test_grade_flow_test_case(client, monkeypatch, with_key):
    fake = FakeClaude({"GradingOut": [GRADING_75]})
    _prepare(client, monkeypatch, fake)
    _download(client)
    assert "valida la clave" in client.post(f"{BASE}/submissions/s2/grade").json()["detail"]
    _validated_key_and_downloads(client)

    assert client.post(f"{BASE}/submissions/s2/grade").json() == {"started": True}
    s2 = client.get(f"{BASE}/download").json()["submissions"]["s2"]
    g = s2["grade"]
    assert g["status"] == "revisada" and g["score"] == 75 and s2["suggested_score"] == 75
    assert g["comment"].startswith("Ejercicio 3: tu procedimiento está bien")
    assert [e["estado"] for e in g["exercises"]] == ["correcto", "correcto", "error_menor", "error_menor"]
    # Se envió la clave y la imagen de la hoja.
    _, _, content = fake.calls[0]
    assert sum(b["type"] == "image" for b in content) == 1
    assert "P(A ∪ B) = 70%" in content[0]["text"]

    # Si cambia la clave, la calificación queda marcada como desactualizada y sin sugerencia.
    client.put(f"{BASE}/key", json={"exercises": KEY[:3]})
    s2 = client.get(f"{BASE}/download").json()["submissions"]["s2"]
    assert s2["grade"]["stale"] and s2["suggested_score"] is None


def test_signed_submission_gets_100_without_calling_the_model(client, monkeypatch, with_key):
    fake = FakeClaude({})
    _prepare(client, monkeypatch, fake)
    client.post("/api/marks", data={"name": "Firma"}, files=[("files", ("f.png", png(signature()), "image/png"))])
    _download(client)
    client.post(f"{BASE}/marks/detect")
    client.post(f"{BASE}/submissions/s1/grade")  # sin clave validada: con marca no hace falta
    s1 = client.get(f"{BASE}/download").json()["submissions"]["s1"]
    assert s1["grade"]["status"] == "con_marca" and s1["suggested_score"] == 100
    assert fake.calls == []


def test_unclear_reading_goes_to_manual_review(client, monkeypatch, with_key):
    out = dict(GRADING_75, ejercicios=[ex("1"), ex("2", legibilidad="parcial"), ex("3"), ex("4")])
    _prepare(client, monkeypatch, FakeClaude({"GradingOut": [out]}))
    _validated_key_and_downloads(client)
    client.post(f"{BASE}/submissions/s2/grade")
    g = client.get(f"{BASE}/download").json()["submissions"]["s2"]["grade"]
    assert g["status"] == "revisar_a_mano" and g["score"] == 75  # el 2 no cuenta como correcto
    assert any("Ejercicio 2" in r for r in g["review_reasons"])


def test_model_failure_marks_only_that_submission(client, monkeypatch, with_key):
    fake = FakeClaude({"GradingOut": [VisionError("Tu cuenta de la API de Claude no tiene crédito"), GRADING_75]})
    _prepare(client, monkeypatch, fake)
    _validated_key_and_downloads(client)
    client.post(f"{BASE}/submissions/s2/grade")
    client.post(f"{BASE}/submissions/s3/grade")
    subs = client.get(f"{BASE}/download").json()["submissions"]
    assert subs["s2"]["grade"]["status"] == "error" and "crédito" in subs["s2"]["grade"]["error"]
    assert subs["s2"]["suggested_score"] is None
    assert subs["s3"]["grade"]["status"] == "revisada"


def test_minor_error_factor_per_assignment(client, monkeypatch, with_key):
    _prepare(client, monkeypatch, FakeClaude({"GradingOut": [GRADING_75]}))
    assert client.get(f"{BASE}/key").json()["minor_error_factor"] == 0.5
    assert client.put(f"{BASE}/grading-settings", json={"minor_error_factor": 1.5}).status_code == 422
    k = client.put(f"{BASE}/grading-settings", json={"minor_error_factor": 0.25}).json()
    assert k["minor_error_factor"] == 0.25 and k["minor_error_factor_override"] == 0.25
    _validated_key_and_downloads(client)
    client.post(f"{BASE}/submissions/s2/grade")
    assert client.get(f"{BASE}/download").json()["submissions"]["s2"]["grade"]["score"] == 62.5


def test_stuck_key_job_expires(client, monkeypatch):
    from datetime import timedelta

    from app.db.models import AnswerKey, utcnow
    from app.db.session import SessionLocal

    _prepare(client, monkeypatch)
    client.put(f"{BASE}/key", json={"exercises": KEY})
    with SessionLocal() as db:
        k = db.query(AnswerKey).one()
        k.job_status = "generando"
        db.commit()
    assert client.get(f"{BASE}/key").json()["state"] == "generando"
    with SessionLocal() as db:
        k = db.query(AnswerKey).one()
        db.execute(AnswerKey.__table__.update().values(updated_at=utcnow() - timedelta(minutes=11)))
        db.commit()
    assert client.get(f"{BASE}/key").json()["state"] == "error"
