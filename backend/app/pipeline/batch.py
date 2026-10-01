"""Etapa 5: procesa una tarea completa con un clic.

1. Descarga las entregas nuevas, cambiadas o con error.
2. Busca la marca del docente (si el módulo está activo en la tarea).
3. Califica: con marca "tarea correcta" → 100; las demás con la clave validada.

Cada paso trata las entregas por separado: si una falla, queda marcada y las demás siguen.
El docente solo interviene en el panel.
"""

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from app.db.models import DL_LISTA, G_CALIFICANDO, G_ERROR, MODE_SOLO_FIRMA, Assignment, Submission
from app.db.session import SessionLocal
from app.files.base import FileSource
from app.grading import grader
from app.marks import service as marks
from app.marks.verifier import Verifier
from app.pipeline import download
from app.vision.claude_client import ClaudeClient, has_api_key

log = logging.getLogger(__name__)

GRADING_WORKERS = 3


@dataclass
class BatchState:
    phase: str  # descargando | marcas | calificando | listo | error
    note: str = ""


_state: dict[int, BatchState] = {}
_lock = threading.Lock()


def state(assignment_id: int) -> BatchState | None:
    with _lock:
        return _state.get(assignment_id)


def is_running(assignment_id: int) -> bool:
    s = state(assignment_id)
    return s is not None and s.phase not in ("listo", "error")


def try_claim(assignment_id: int) -> bool:
    with _lock:
        s = _state.get(assignment_id)
        if s is not None and s.phase not in ("listo", "error"):
            return False
        _state[assignment_id] = BatchState("descargando")
        return True


def _set(assignment_id: int, phase: str, note: str = "") -> None:
    with _lock:
        _state[assignment_id] = BatchState(phase, note)


def needs_grading(sub: Submission) -> bool:
    if sub.download_status != DL_LISTA:
        return False
    g = sub.grade
    if g is None or g.status == G_ERROR:
        return True
    key = sub.assignment.answer_key
    stale = key is not None and g.key_version is not None and g.key_version != key.version and g.status != "con_marca"
    # Una entrega que ya tiene marca confirmada no necesita más; una que perdió la marca, sí.
    if g.status == "con_marca" and marks.effective_status(sub) != "con_marca":
        return True
    if g.status != "con_marca" and marks.effective_status(sub) == "con_marca":
        return True
    return stale


def run_all(
    assignment_id: int,
    source_factory: Callable[[], FileSource],
    verifier_factory: Callable[[], Verifier],
    client_factory: Callable[[], ClaudeClient],
) -> None:
    """Requiere haber llamado try_claim()."""
    notes: list[str] = []
    try:
        # 1) Descarga
        if download.try_claim(assignment_id):
            download.run_downloads(assignment_id, source_factory)

        # 2) Marcas
        _set(assignment_id, "marcas")
        with SessionLocal() as db:
            a = db.get(Assignment, assignment_id)
            module_on = a.mark_module_enabled
            has_marks = bool(marks.active_marks(db, a.teacher_id))
        if module_on and has_marks and marks.try_claim(assignment_id):
            marks.run_mark_detection(assignment_id, verifier_factory)
        elif module_on and not has_marks:
            notes.append("No tienes una marca configurada: configúrala en «Mi marca»")

        # 3) Calificación (en modo «solo firma» no hay nada más que calcular: lo hace el panel)
        with SessionLocal() as db:
            if db.get(Assignment, assignment_id).grading_mode == MODE_SOLO_FIRMA:
                _set(assignment_id, "listo", ". ".join(notes))
                return
        _set(assignment_id, "calificando")
        with SessionLocal() as db:
            a = db.get(Assignment, assignment_id)
            key_ok = a.answer_key is not None and a.answer_key.validated_at is not None
            model_ok = has_api_key()
            to_grade = []
            skipped = 0
            for sub in a.submissions:
                if not needs_grading(sub):
                    continue
                signed = marks.effective_status(sub) == "con_marca"
                if signed or (key_ok and model_ok):
                    grader.mark_as_grading(db, sub)
                    to_grade.append(sub.id)
                else:
                    skipped += 1
        if skipped:
            if not key_ok:
                notes.append(f"{skipped} entregas sin marca esperan a que valides la clave de respuestas")
            elif not model_ok:
                notes.append(f"{skipped} entregas sin marca necesitan la clave de la API de Claude para calificarse")
        if to_grade:
            client = None if not model_ok else client_factory()
            with ThreadPoolExecutor(max_workers=GRADING_WORKERS) as pool:
                list(pool.map(lambda i: grader.grade_submission(i, lambda: client), to_grade))
        _set(assignment_id, "listo", ". ".join(notes))
        log.info("Tarea %s procesada: %s calificadas", assignment_id, len(to_grade))
    except Exception:
        log.exception("Falló el procesamiento de la tarea %s", assignment_id)
        _set(assignment_id, "error", "Error inesperado; vuelve a intentarlo")
        with SessionLocal() as db:  # no dejar entregas colgadas en "calificando"
            for sub in db.get(Assignment, assignment_id).submissions:
                if sub.grade is not None and sub.grade.status == G_CALIFICANDO:
                    sub.grade.status, sub.grade.error = G_ERROR, "Se interrumpió; vuelve a procesar"
            db.commit()
