"""Califica una entrega: marca "tarea correcta" → 100; si no, el modelo lee cada ejercicio.

Si falla, la entrega queda con estado "error" y el motivo; nunca se inventa una calificación.
"""

import json
import logging
from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session

from app.answer_key.service import exercises_of
from app.config import get_settings
from app.db.models import (
    DL_LISTA,
    G_CALIFICANDO,
    G_CON_MARCA,
    G_ERROR,
    G_REVISADA,
    G_REVISAR,
    MK_CON_MARCA,
    MK_DUDOSA,
    MK_ERROR,
    Grade,
    Submission,
    Teacher,
)
from app.db.session import SessionLocal
from app.grading import prompts
from app.grading.schemas import GradingOut
from app.grading.scoring import compute
from app.marks.service import effective_status
from app.vision.claude_client import ClaudeClient, VisionError, image_block, text_block

log = logging.getLogger(__name__)


class GradingBlocked(ValueError):
    """No se puede calificar todavía (sin clave validada, sin imágenes…)."""


def minor_factor_for(sub: Submission, teacher: Teacher) -> float:
    if sub.assignment.minor_error_factor is not None:
        return sub.assignment.minor_error_factor
    ts = teacher.settings
    if ts and ts.minor_error_factor is not None:
        return ts.minor_error_factor
    return get_settings().minor_error_factor


def min_confidence_for(teacher: Teacher) -> float:
    ts = teacher.settings
    if ts and ts.exercise_min_confidence is not None:
        return ts.exercise_min_confidence
    return get_settings().exercise_min_confidence


def check_can_grade(sub: Submission) -> None:
    key = sub.assignment.answer_key
    if effective_status(sub) == MK_CON_MARCA:
        return  # con marca "tarea correcta" no hace falta clave
    if key is None or key.validated_at is None:
        raise GradingBlocked("Primero valida la clave de respuestas")
    if sub.download_status != DL_LISTA or not sub.pages:
        raise GradingBlocked("Primero descarga la entrega")


def mark_as_grading(db: Session, sub: Submission) -> None:
    if sub.grade is None:
        sub.grade = Grade()
    sub.grade.status, sub.grade.error = G_CALIFICANDO, None
    db.commit()


def _grade(db: Session, sub: Submission, client: ClaudeClient) -> None:
    grade = sub.grade
    if effective_status(sub) == MK_CON_MARCA:
        grade.status, grade.score = G_CON_MARCA, 100.0
        grade.comment, grade.review_reasons, grade.detail_json = None, None, "[]"
        grade.key_version = sub.assignment.answer_key.version if sub.assignment.answer_key else None
        return

    key = sub.assignment.answer_key
    exercises = exercises_of(key)
    teacher = db.get(Teacher, sub.assignment.teacher_id)
    data_dir = Path(get_settings().data_dir)

    content: list[dict] = [text_block("Clave de respuestas validada por el docente:\n" + prompts.key_as_text(exercises))]
    content.append(text_block(f"Hojas del alumno ({len(sub.pages)} páginas):"))
    for page in sub.pages:
        content.append(text_block(f"Página {page.index + 1}:"))
        content.append(image_block((data_dir / page.path).read_bytes()))
    content.append(text_block("Revisa cada ejercicio de la clave en estas hojas."))

    out, usage = client.structured(prompts.GRADING_SYSTEM, content, GradingOut, purpose=f"calificar entrega {sub.id}")
    try:
        result = compute(exercises, out, minor_factor_for(sub, teacher), min_confidence_for(teacher))
    except ValueError as exc:
        raise VisionError(f"Respuesta del modelo no válida: {exc}") from exc

    reasons = list(result.review_reasons)
    if effective_status(sub) in (MK_DUDOSA, MK_ERROR):
        reasons.insert(0, "Hay una posible marca por confirmar")
    grade.status = G_REVISAR if reasons else G_REVISADA
    grade.score = result.score
    grade.comment = result.comment
    grade.review_reasons = "\n".join(reasons) or None
    grade.detail_json = json.dumps(result.detail(), ensure_ascii=False)
    grade.key_version = key.version
    grade.model = client.model
    grade.input_tokens, grade.output_tokens = usage.input_tokens, usage.output_tokens


def grade_submission(submission_id: int, client_factory: Callable[[], ClaudeClient]) -> None:
    """Califica una entrega ya marcada como 'calificando'. Nunca lanza."""
    with SessionLocal() as db:
        sub = db.get(Submission, submission_id)
        if sub is None or sub.grade is None:
            return
        try:
            check_can_grade(sub)
            _grade(db, sub, client_factory() if effective_status(sub) != MK_CON_MARCA else None)
            sub.grade.error = None
            db.commit()
            log.info("Entrega %s calificada: %s", sub.id, sub.grade.status)
        except (VisionError, GradingBlocked) as exc:
            _fail(db, submission_id, str(exc))
        except Exception:
            log.exception("Error inesperado al calificar la entrega %s", submission_id)
            _fail(db, submission_id, "Error inesperado al calificar")


def _fail(db: Session, submission_id: int, message: str) -> None:
    db.rollback()
    grade = db.get(Submission, submission_id).grade
    grade.status, grade.error = G_ERROR, message
    db.commit()
    log.warning("Entrega %s sin calificar: %s", submission_id, message)



def reset_interrupted(db: Session) -> None:
    for g in db.query(Grade).filter_by(status=G_CALIFICANDO):
        g.status, g.error = G_ERROR, "Se interrumpió; vuelve a calificar"
    db.commit()
