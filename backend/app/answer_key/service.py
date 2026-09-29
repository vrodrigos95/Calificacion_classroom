"""Clave de respuestas: captura manual, extracción de la clave del docente o resolución por el modelo.

Regla: nunca se califica con una clave sin validar. Cualquier cambio a los ejercicios quita
la validación y sube la versión.
"""

import json
import logging
import re
import unicodedata
from datetime import timedelta, timezone
from collections.abc import Callable
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import (
    DL_LISTA,
    KEY_DOCENTE,
    KEY_RESUELTA,
    KJ_ERROR,
    KJ_GENERANDO,
    KJ_LISTA,
    AnswerKey,
    Assignment,
    Submission,
    utcnow,
)
from app.db.session import SessionLocal
from app.files.base import FileFetchError, FileSource
from app.grading import prompts
from app.grading.schemas import KeyExercise, KeyModelOut, StatementOut
from app.imaging.convert import UnsupportedFile, to_pages
from app.vision.claude_client import ClaudeClient, VisionError, image_block, text_block

log = logging.getLogger(__name__)

MAX_KEY_PAGES = 10
STATEMENT_SAMPLES = 4
PAGES_PER_SAMPLE = 2
SIMILARITY_MIN = 0.6


class KeyValidationError(ValueError):
    """Error de validación de la clave, con mensaje para el docente."""


def get_or_create(db: Session, assignment: Assignment) -> AnswerKey:
    if assignment.answer_key is None:
        assignment.answer_key = AnswerKey()
        db.flush()
    return assignment.answer_key


def exercises_of(key: AnswerKey | None) -> list[KeyExercise]:
    if key is None:
        return []
    return [KeyExercise.model_validate(e) for e in json.loads(key.exercises_json)]


def set_exercises(
    key: AnswerKey,
    exercises: list[KeyExercise],
    *,
    source: str | None = None,
    statement_source: str | None = None,
    warning: str | None = None,
) -> None:
    """Guarda los ejercicios. Siempre quita la validación: hay que volver a validar."""
    key.exercises_json = json.dumps([e.model_dump() for e in exercises], ensure_ascii=False)
    key.version = (key.version or 0) + 1
    key.validated_at = None
    if source:
        key.source = source
    key.statement_source = statement_source if source else key.statement_source
    key.warning = warning


JOB_TIMEOUT = timedelta(minutes=10)


def _stuck(key: AnswerKey) -> bool:
    """Un trabajo 'generando' que lleva demasiado tiempo se da por fallido (p. ej. se cortó)."""
    updated = key.updated_at if key.updated_at.tzinfo else key.updated_at.replace(tzinfo=timezone.utc)
    return utcnow() - updated > JOB_TIMEOUT


def key_state(key: AnswerKey | None) -> str:
    """sin_clave | generando | error | sin_validar | validada"""
    if key is None:
        return "sin_clave"
    if key.job_status == KJ_GENERANDO:
        return "error" if _stuck(key) else "generando"
    has_exercises = bool(exercises_of(key))
    if key.job_status == KJ_ERROR and not has_exercises:
        return "error"
    if not has_exercises:
        return "sin_clave"
    return "validada" if key.validated_at else "sin_validar"


def validate(key: AnswerKey) -> None:
    exercises = exercises_of(key)
    if key.job_status == KJ_GENERANDO and not _stuck(key):
        raise KeyValidationError("Espera a que termine de generarse la clave")
    if not exercises:
        raise KeyValidationError("La clave no tiene ejercicios")
    nums = [e.numero.strip() for e in exercises]
    if any(not n for n in nums):
        raise KeyValidationError("Todos los ejercicios necesitan número")
    if len(set(nums)) != len(nums):
        raise KeyValidationError("Hay números de ejercicio repetidos")
    missing = [e.numero for e in exercises if not e.respuesta_final.strip()]
    if missing:
        raise KeyValidationError("Falta la respuesta del ejercicio " + ", ".join(missing))
    key.validated_at = utcnow()


def _clean(exercises) -> list[KeyExercise]:
    return [KeyExercise.model_validate(e.model_dump(exclude={"confianza"})) for e in exercises]


def _low_confidence(out: KeyModelOut) -> str | None:
    low = [e.numero for e in out.ejercicios if not 0 <= e.confianza <= 1 or e.confianza < 0.8]
    parts = []
    if low:
        parts.append("Revisa con cuidado los ejercicios " + ", ".join(low) + " (el modelo no está seguro)")
    if out.observaciones.strip():
        parts.append(out.observaciones.strip())
    return ". ".join(parts) or None


def _file_blocks(files: list[tuple[bytes, str]]) -> list[dict]:
    blocks = []
    n = 0
    for data, mime in files:
        for page in to_pages(data, mime):
            n += 1
            if n > MAX_KEY_PAGES:
                raise KeyValidationError(f"La clave tiene más de {MAX_KEY_PAGES} páginas")
            blocks.append(text_block(f"Página {n}:"))
            blocks.append(image_block(page.jpeg))
    return blocks


# ---- Trabajos en segundo plano ------------------------------------------------------------

def _start_job(db: Session, key: AnswerKey) -> None:
    if key.job_status == KJ_GENERANDO and not _stuck(key):
        raise KeyValidationError("Ya se está generando la clave")
    key.job_status, key.job_error = KJ_GENERANDO, None
    db.commit()


def _finish(key_id: int, fn: Callable[[Session, AnswerKey], None]) -> None:
    with SessionLocal() as db:
        key = db.get(AnswerKey, key_id)
        try:
            fn(db, key)
            key.job_status, key.job_error = KJ_LISTA, None
        except (VisionError, KeyValidationError, UnsupportedFile, FileFetchError) as exc:
            db.rollback()
            key = db.get(AnswerKey, key_id)
            key.job_status, key.job_error = KJ_ERROR, str(exc)
        except Exception:
            log.exception("Error inesperado al generar la clave %s", key_id)
            db.rollback()
            key = db.get(AnswerKey, key_id)
            key.job_status, key.job_error = KJ_ERROR, "Error inesperado al generar la clave"
        db.commit()


def start_from_teacher(db: Session, key: AnswerKey) -> None:
    _start_job(db, key)


def run_from_teacher(
    key_id: int, text: str, files: list[tuple[bytes, str]], client_factory: Callable[[], ClaudeClient]
) -> None:
    """Modo a: el docente sube su clave (texto, foto o PDF) y el modelo la estructura."""

    def work(db: Session, key: AnswerKey) -> None:
        content: list[dict] = []
        if text.strip():
            content.append(text_block("Clave escrita por el docente:\n" + text.strip()))
        content.extend(_file_blocks(files))
        if not content:
            raise KeyValidationError("Escribe la clave o sube un archivo")
        content.append(text_block("Extrae la clave de respuestas."))
        out, _ = client_factory().structured(
            prompts.KEY_FROM_TEACHER_SYSTEM, content, KeyModelOut, purpose="extraer clave del docente"
        )
        if not out.ejercicios:
            raise KeyValidationError("No se encontraron ejercicios en la clave que subiste")
        set_exercises(key, _clean(out.ejercicios), source=KEY_DOCENTE, statement_source=None,
                      warning=_low_confidence(out))

    _finish(key_id, work)


@dataclass
class ClassroomStatement:
    description: str
    material_file_ids: list[str]


def _norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-z%]+", " ", s)).strip()


def compare_statements(samples: list[list[tuple[str, str]]]) -> list[str]:
    """Diferencias entre los enunciados que muestran distintos alumnos (vacío = consistentes)."""
    diffs = []
    base = samples[0]
    for i, other in enumerate(samples[1:], start=2):
        if len(other) != len(base):
            diffs.append(f"la hoja {i} tiene {len(other)} ejercicios y la hoja 1 tiene {len(base)}")
            continue
        for (n1, e1), (_, e2) in zip(base, other):
            ratio = SequenceMatcher(None, _norm_text(e1), _norm_text(e2)).ratio()
            if ratio < SIMILARITY_MIN:
                diffs.append(f"el ejercicio {n1} de la hoja {i} parece distinto")
    return diffs


def _statement_call(client: ClaudeClient, content: list[dict], purpose: str) -> StatementOut:
    out, _ = client.structured(prompts.STATEMENT_SYSTEM, content, StatementOut, purpose=purpose)
    return out


def run_solve(
    key_id: int,
    classroom: ClassroomStatement,
    source_factory: Callable[[], FileSource],
    client_factory: Callable[[], ClaudeClient],
) -> None:
    """Modo b: busca el enunciado (Classroom y, si no está, las hojas de los alumnos) y lo resuelve."""

    def work(db: Session, key: AnswerKey) -> None:
        client = client_factory()
        statements: list[tuple[str, str]] = []
        origin = None
        warning_parts: list[str] = []

        # 1) Classroom: descripción y adjuntos de la tarea.
        content: list[dict] = []
        if classroom.description.strip():
            content.append(text_block("Descripción de la tarea en Classroom:\n" + classroom.description.strip()))
        if classroom.material_file_ids:
            source = source_factory()
            files = []
            for fid in classroom.material_file_ids:
                f = source.fetch(fid)
                files.append((f.data, f.mime_type))
            content.extend(_file_blocks(files))
        if content:
            out = _statement_call(client, content + [text_block("Extrae los enunciados.")], "enunciado en Classroom")
            if out.enunciado_encontrado and out.ejercicios:
                statements = [(e.numero, e.enunciado) for e in out.ejercicios]
                origin = "classroom"

        # 2) Hojas de los alumnos, si Classroom no tiene el enunciado.
        if not statements:
            subs = (
                db.query(Submission)
                .filter_by(assignment_id=key.assignment_id, download_status=DL_LISTA)
                .order_by(Submission.id)
                .limit(STATEMENT_SAMPLES)
                .all()
            )
            if not subs:
                raise KeyValidationError(
                    "La tarea no tiene enunciado en Classroom. Descarga las entregas para buscarlo en las hojas."
                )
            samples = []
            data_dir = Path(get_settings().data_dir)
            for i, sub in enumerate(subs, start=1):
                blocks = []
                for page in sub.pages[:PAGES_PER_SAMPLE]:
                    blocks.append(image_block((data_dir / page.path).read_bytes()))
                out = _statement_call(
                    client, blocks + [text_block("Extrae los enunciados de esta hoja.")], f"enunciado en hoja {i}"
                )
                if out.enunciado_encontrado and out.ejercicios:
                    samples.append([(e.numero, e.enunciado) for e in out.ejercicios])
            if not samples:
                raise KeyValidationError("No se encontraron enunciados ni en Classroom ni en las hojas de los alumnos")
            diffs = compare_statements(samples)
            if diffs:
                warning_parts.append(
                    "⚠️ Distintos alumnos muestran enunciados diferentes: " + "; ".join(diffs)
                    + ". Revisa la clave antes de validarla."
                )
            statements = samples[0]
            origin = "hojas_de_alumnos"

        # 3) Resolver.
        solve_content = [
            text_block("Ejercicios a resolver:\n" + prompts.statements_as_text(statements)),
            text_block("Resuélvelos."),
        ]
        out, _ = client.structured(prompts.SOLVE_SYSTEM, solve_content, KeyModelOut, purpose="resolver ejercicios")
        exercises = _clean(out.ejercicios)
        by_num = dict(statements)
        for e in exercises:  # conserva el enunciado tal como se encontró
            e.enunciado = e.enunciado or by_num.get(e.numero, "")
        low = _low_confidence(out)
        if low:
            warning_parts.append(low)
        set_exercises(key, exercises, source=KEY_RESUELTA, statement_source=origin,
                      warning=" ".join(warning_parts) or None)

    _finish(key_id, work)


def reset_interrupted(db: Session) -> None:
    for key in db.query(AnswerKey).filter_by(job_status=KJ_GENERANDO):
        key.job_status, key.job_error = KJ_ERROR, "Se interrumpió; vuelve a intentarlo"
    db.commit()
