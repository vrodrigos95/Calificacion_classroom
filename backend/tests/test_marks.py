import io
import json
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.db.models import (
    MK_CON_MARCA,
    MK_DUDOSA,
    MK_ERROR,
    MK_SIN_MARCA,
    Assignment,
    Page,
    Submission,
    Teacher,
    TeacherSettings,
)
from app.db.session import SessionLocal
from app.marks import service
from app.marks.color import find_candidates, profile_from_references
from app.marks.verifier import (
    CandidateVerdict,
    ClaudeVerifier,
    LocalVerifier,
    MarkVerificationOut,
    VerificationError,
)
from tests.helpers import PRIVATE

GREEN = (90, 170, 130)
REAL = pytest.mark.skipif(not (PRIVATE / "firma_ref_1.png").exists(), reason="sin archivos reales")


def signature(color=GREEN, size=(120, 180)) -> Image.Image:
    im = Image.new("RGB", size, (250, 250, 247))
    d = ImageDraw.Draw(im)
    d.ellipse([(20, 20), (100, 160)], outline=color, width=4)
    d.line([(60, 40), (60, 120)], fill=color, width=4)
    return im


def png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def page_with(marks: list[tuple[int, int]], color=GREEN, extra=None) -> Image.Image:
    """Hoja con cuadrícula azul, texto rosa y firmas en las posiciones dadas."""
    im = Image.new("RGB", (1200, 1600), (246, 246, 242))
    d = ImageDraw.Draw(im)
    for y in range(60, 1600, 40):
        d.line([(0, y), (1200, y)], fill=(185, 195, 235), width=2)
    d.text((100, 120), "PREGUNTAS DE PROBABILIDAD", fill=(210, 60, 140))
    d.text((100, 300), "P(A) = 2/6 = 33%", fill=(60, 50, 140))
    for x, y in marks:
        im.paste(signature(color), (x, y))
    if extra:
        extra(d)
    return im


# ---- Prefiltro por color --------------------------------------------------------------

@REAL
def test_real_references_give_a_green_profile():
    refs = [np.array(Image.open(PRIVATE / f"firma_ref_{i}.png").convert("RGBA")) for i in (1, 2, 3)]
    prof = profile_from_references(refs)
    assert prof.colored and prof.da < -0.9  # a* negativo = verde


@REAL
@pytest.mark.parametrize("sheet", ["entrega_firmada.webp", "entrega_firmada_2.jpg"])
def test_real_sheets_have_one_candidate_on_the_signature(sheet):
    refs = [np.array(Image.open(PRIVATE / f"firma_ref_{i}.png").convert("RGBA")) for i in (1, 2, 3)]
    prof = profile_from_references(refs)
    page = np.array(Image.open(PRIVATE / sheet).convert("RGB"))
    cands = find_candidates(page, prof)
    assert len(cands) == 1
    h, w = page.shape[:2]
    c = cands[0]
    assert c.x0 > 0.7 * w and c.y1 < 0.25 * h  # esquina superior derecha, donde está la firma


def test_no_green_means_no_candidates():
    prof = profile_from_references([np.array(signature())])
    assert find_candidates(np.array(page_with([])), prof) == []


def test_black_reference_is_not_colored():
    prof = profile_from_references([np.array(signature(color=(30, 30, 30)))])
    assert not prof.colored
    assert find_candidates(np.array(page_with([(900, 100)])), prof) == []


def test_other_ink_colors_are_ignored_by_a_blue_profile():
    blue = (40, 70, 200)
    prof = profile_from_references([np.array(signature(color=blue))])
    assert prof.colored
    # La página tiene firma verde y cuadrícula azul claro: nada de eso es tinta azul fuerte.
    assert find_candidates(np.array(page_with([(900, 100)])), prof) == []
    assert len(find_candidates(np.array(page_with([(900, 100)], color=blue)), prof)) == 1


# ---- Servicio de detección --------------------------------------------------------------

class FakeVerifier:
    name = "claude"

    def __init__(self, confidence=0.95, is_mark=True, error=None):
        self.confidence, self.is_mark, self.error = confidence, is_mark, error
        self.calls = []

    def verify(self, refs, crops):
        self.calls.append((refs, crops))
        if self.error:
            raise VerificationError(self.error)
        return [CandidateVerdict(c.candidate_id, self.is_mark, None, self.confidence, "ok", "claude") for c in crops]


def _setup(db, pages: list[Image.Image], meaning="correcta", zone="primera", mark_enabled=True):
    t = Teacher(google_sub="s", email="d@x", name="D", settings=TeacherSettings())
    db.add(t)
    db.commit()
    mark = service.create_mark(db, t, "Firma verde", meaning, zone, [png(signature())])
    a = Assignment(teacher_id=t.id, course_id="c1", coursework_id="w1", mark_module_enabled=mark_enabled)
    sub = Submission(classroom_submission_id="s1", student_user_id="u1", student_name="A B", download_status="lista")
    a.submissions.append(sub)
    db.add(a)
    db.flush()
    from app.config import get_settings
    from pathlib import Path

    folder = Path(get_settings().data_dir) / "pages" / str(sub.id)
    folder.mkdir(parents=True, exist_ok=True)
    for i, img in enumerate(pages):
        rel = f"pages/{sub.id}/{i:03d}.jpg"
        img.save(Path(get_settings().data_dir) / rel, "JPEG", quality=92)
        sub.pages.append(Page(index=i, path=rel, width=img.width, height=img.height, source_file_id="f"))
    db.commit()
    return t, mark, sub


TH = service.Thresholds(accept=0.85, doubtful=0.60)


@pytest.mark.parametrize(
    "conf,is_mark,expected",
    [(0.95, True, MK_CON_MARCA), (0.85, True, MK_CON_MARCA), (0.84, True, MK_DUDOSA), (0.6, True, MK_DUDOSA),
     (0.59, True, MK_SIN_MARCA), (0.99, False, MK_SIN_MARCA)],
)
def test_thresholds_never_give_100_to_a_doubtful_match(conf, is_mark, expected):
    with SessionLocal() as db:
        _, mark, sub = _setup(db, [page_with([(950, 80)])])
        service.detect_in_submission(db, sub, [mark], FakeVerifier(conf, is_mark), TH)
        assert sub.mark_status == expected
        if expected != MK_SIN_MARCA:
            assert sub.detections[0].crop_path.endswith(".jpg")


def test_local_verifier_never_accepts_alone():
    with SessionLocal() as db:
        _, mark, sub = _setup(db, [page_with([(950, 80)])])
        service.detect_in_submission(db, sub, [mark], LocalVerifier(), TH)
        assert sub.mark_status == MK_DUDOSA
        assert "confírmala" in sub.mark_detail
        # El docente confirma con el recorte a la vista.
        sub.mark_confirmed = True
        assert service.effective_status(sub) == MK_CON_MARCA


def test_verification_error_goes_to_manual_review_with_crop():
    with SessionLocal() as db:
        _, mark, sub = _setup(db, [page_with([(950, 80)])])
        service.detect_in_submission(db, sub, [mark], FakeVerifier(error="Tu cuenta no tiene crédito"), TH)
        assert sub.mark_status == MK_ERROR and "crédito" in sub.mark_detail
        assert sub.detections and sub.detections[0].verdict == "dudosa"


def test_first_page_zone_ignores_later_pages_but_any_page_zone_does_not():
    pages = [page_with([]), page_with([(950, 80)])]
    with SessionLocal() as db:
        _, mark, sub = _setup(db, pages, zone="primera")
        v = FakeVerifier()
        service.detect_in_submission(db, sub, [mark], v, TH)
        assert sub.mark_status == MK_SIN_MARCA and v.calls == []

        mark.zone = "cualquiera"
        service.detect_in_submission(db, sub, [mark], v, TH)
        assert sub.mark_status == MK_CON_MARCA
        assert sub.detections[0].page_index == 1


def test_mark_on_first_page_covers_whole_multi_page_submission():
    with SessionLocal() as db:
        _, mark, sub = _setup(db, [page_with([(950, 80)]), page_with([]), page_with([])])
        service.detect_in_submission(db, sub, [mark], FakeVerifier(), TH)
        assert sub.mark_status == MK_CON_MARCA


def test_informative_mark_is_shown_but_does_not_give_100():
    with SessionLocal() as db:
        _, mark, sub = _setup(db, [page_with([(950, 80)])], meaning="informativa")
        service.detect_in_submission(db, sub, [mark], FakeVerifier(), TH)
        assert sub.mark_status == MK_SIN_MARCA
        assert [d.verdict for d in sub.detections] == ["marca"]


def test_batch_respects_module_toggle_and_teacher_decisions():
    with SessionLocal() as db:
        t, mark, sub = _setup(db, [page_with([(950, 80)])], mark_enabled=False)
        a_id, sub_id = sub.assignment_id, sub.id
    assert service.try_claim(a_id)
    service.run_mark_detection(a_id, lambda: FakeVerifier())
    with SessionLocal() as db:
        sub = db.get(Submission, sub_id)
        assert sub.mark_status == "desactivado"
        sub.assignment.mark_module_enabled = True
        db.commit()
    assert service.try_claim(a_id)
    service.run_mark_detection(a_id, lambda: FakeVerifier())
    with SessionLocal() as db:
        sub = db.get(Submission, sub_id)
        assert sub.mark_status == MK_CON_MARCA
        sub.mark_confirmed = False  # el docente dice que no es su firma
        db.commit()
    assert service.try_claim(a_id)
    service.run_mark_detection(a_id, lambda: FakeVerifier())  # no pisa la decisión del docente
    with SessionLocal() as db:
        assert service.effective_status(db.get(Submission, sub_id)) == MK_SIN_MARCA


# ---- ClaudeVerifier con un cliente simulado ------------------------------------------------

class FakeAnthropic:
    def __init__(self, response=None, exc=None):
        self.kwargs = None
        outer = self

        class _Messages:
            def parse(self, **kwargs):
                outer.kwargs = kwargs
                if exc:
                    raise exc
                return response

        self.beta = SimpleNamespace(messages=_Messages())


def _resp(items, stop="end_turn"):
    parsed = MarkVerificationOut.model_validate({"candidatos": items}) if items is not None else None
    return SimpleNamespace(stop_reason=stop, parsed_output=parsed, usage=SimpleNamespace(input_tokens=900, output_tokens=120))


def _refs_crops():
    from app.marks.verifier import CandidateCrop, ReferenceSet

    return [ReferenceSet(7, "Firma verde", [png(signature())])], [
        CandidateCrop("m7_p1_c1", png(signature())),
        CandidateCrop("m7_p1_c2", png(signature())),
    ]


def test_claude_verifier_request_and_parsing():
    client = FakeAnthropic(
        _resp(
            [
                {"candidato_id": "m7_p1_c1", "es_marca": True, "marca_referencia_id": None, "confianza": 0.93, "motivo": "mismo lazo"},
                {"candidato_id": "otro", "es_marca": True, "marca_referencia_id": 7, "confianza": 1, "motivo": "inventado"},
            ]
        )
    )
    refs, crops = _refs_crops()
    out = {v.candidate_id: v for v in ClaudeVerifier(client, model="claude-opus-5").verify(refs, crops)}
    assert out["m7_p1_c1"].mark_id == 7 and out["m7_p1_c1"].confidence == 0.93
    assert "otro" not in out  # ignora ids que no pedimos
    assert out["m7_p1_c2"].confidence == 0.6  # omitido por el modelo: queda dudoso, nunca aceptado
    k = client.kwargs
    assert k["model"] == "claude-opus-5" and k["output_format"] is MarkVerificationOut
    assert k["fallbacks"] == "default" and k["betas"] == ["server-side-fallback-2026-07-01"]
    images = [b for b in k["messages"][0]["content"] if b["type"] == "image"]
    assert len(images) == 3  # 1 referencia + 2 candidatos


def test_claude_verifier_without_fallback_for_other_models():
    client = FakeAnthropic(_resp([]))
    refs, crops = _refs_crops()
    ClaudeVerifier(client, model="claude-sonnet-5").verify(refs, crops)
    assert "fallbacks" not in client.kwargs


@pytest.mark.parametrize(
    "response,match",
    [
        (_resp(None, stop="refusal"), "se negó"),
        (_resp(None, stop="max_tokens"), "completa"),
        (_resp([{"candidato_id": "m7_p1_c1", "es_marca": True, "marca_referencia_id": 7, "confianza": 1.4, "motivo": "x"}]), "fuera de rango"),
    ],
)
def test_claude_verifier_bad_answers_raise(response, match):
    refs, crops = _refs_crops()
    with pytest.raises(VerificationError, match=match):
        ClaudeVerifier(FakeAnthropic(response), model="claude-opus-5").verify(refs, crops)


def test_claude_verifier_api_errors_become_clear_messages():
    import anthropic
    import httpx2 as httpx

    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    err = anthropic.AuthenticationError("bad key", response=httpx.Response(401, request=req), body=None)
    refs, crops = _refs_crops()
    with pytest.raises(VerificationError, match="clave"):
        ClaudeVerifier(FakeAnthropic(exc=err), model="claude-opus-5").verify(refs, crops)


def test_profile_is_stored_as_json():
    with SessionLocal() as db:
        _, mark, _ = _setup(db, [page_with([])])
        assert json.loads(mark.profile_json)["colored"] is True
