from collections.abc import Callable
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.answer_key import service as keys
from app.api.deps import classroom_reader, current_teacher
from app.api.downloads import SourceFactory, file_source_factory
from app.api.marks import _assignment, _own_submission
from app.classroom.client import ClassroomReader
from app.config import get_settings
from app.db.models import KJ_GENERANDO, Assignment, Teacher
from app.db.session import get_db
from app.grading import grader
from app.grading.schemas import KeyExercise
from app.vision.claude_client import ClaudeClient, has_api_key

router = APIRouter(prefix="/api/courses/{course_id}/coursework/{coursework_id}", tags=["calificación"])

ClientFactory = Callable[[], ClaudeClient]


def claude_factory() -> ClientFactory:
    return ClaudeClient


def _require_model():
    if not has_api_key():
        raise HTTPException(
            status_code=409,
            detail="Esta función usa Claude: agrega ANTHROPIC_API_KEY en backend\\.env y reinicia la app",
        )


KeyState = Literal["sin_clave", "generando", "error", "sin_validar", "validada"]


class KeyOut(BaseModel):
    state: KeyState
    exercises: list[KeyExercise]
    source: str | None
    statement_source: str | None
    warning: str | None
    job_error: str | None
    version: int | None
    validated_at: datetime | None
    model_available: bool
    minor_error_factor: float  # el que se aplica en esta tarea
    minor_error_factor_override: float | None  # None = usa el del docente
    teacher_minor_error_factor: float


def _key_out(a: Assignment | None, teacher: Teacher) -> KeyOut:
    key = a.answer_key if a else None
    ts = teacher.settings
    teacher_factor = ts.minor_error_factor if ts and ts.minor_error_factor is not None else get_settings().minor_error_factor
    override = a.minor_error_factor if a else None
    return KeyOut(
        state=keys.key_state(key),
        exercises=keys.exercises_of(key),
        source=key.source if key else None,
        statement_source=key.statement_source if key else None,
        warning=key.warning if key else None,
        job_error=key.job_error if key else None,
        version=key.version if key else None,
        validated_at=key.validated_at if key else None,
        model_available=has_api_key(),
        minor_error_factor=override if override is not None else teacher_factor,
        minor_error_factor_override=override,
        teacher_minor_error_factor=teacher_factor,
    )


@router.get("/key", response_model=KeyOut)
def get_key(course_id: str, coursework_id: str, teacher: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    return _key_out(_assignment(db, teacher, course_id, coursework_id), teacher)


class KeyIn(BaseModel):
    exercises: list[KeyExercise]


@router.put("/key", response_model=KeyOut)
def put_key(
    course_id: str,
    coursework_id: str,
    body: KeyIn,
    teacher: Teacher = Depends(current_teacher),
    db: Session = Depends(get_db),
):
    """Captura o corrección manual de la clave (quita la validación)."""
    a = _assignment(db, teacher, course_id, coursework_id, create=True)
    key = keys.get_or_create(db, a)
    if key.job_status == KJ_GENERANDO:
        raise HTTPException(status_code=409, detail="Espera a que termine de generarse la clave")
    keys.set_exercises(key, body.exercises, warning=key.warning)
    db.commit()
    return _key_out(a, teacher)


@router.post("/key/validate", response_model=KeyOut)
def validate_key(course_id: str, coursework_id: str, teacher: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    a = _assignment(db, teacher, course_id, coursework_id)
    if a is None or a.answer_key is None:
        raise HTTPException(status_code=409, detail="Todavía no hay clave")
    try:
        keys.validate(a.answer_key)
    except keys.KeyValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return _key_out(a, teacher)


@router.post("/key/from-teacher", response_model=KeyOut)
async def key_from_teacher(
    course_id: str,
    coursework_id: str,
    background: BackgroundTasks,
    text: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    teacher: Teacher = Depends(current_teacher),
    db: Session = Depends(get_db),
    make_client: ClientFactory = Depends(claude_factory),
):
    """Modo a: el docente sube su clave (texto, foto o PDF); el modelo la estructura."""
    _require_model()
    payload = [(await f.read(), f.content_type or "") for f in files]
    if not text.strip() and not payload:
        raise HTTPException(status_code=400, detail="Escribe la clave o sube un archivo")
    a = _assignment(db, teacher, course_id, coursework_id, create=True)
    key = keys.get_or_create(db, a)
    try:
        keys.start_from_teacher(db, key)
    except keys.KeyValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    background.add_task(keys.run_from_teacher, key.id, text, payload, make_client)
    return _key_out(a, teacher)


@router.post("/key/solve", response_model=KeyOut)
def key_solve(
    course_id: str,
    coursework_id: str,
    background: BackgroundTasks,
    teacher: Teacher = Depends(current_teacher),
    db: Session = Depends(get_db),
    reader: ClassroomReader = Depends(classroom_reader),
    source_factory: SourceFactory = Depends(file_source_factory),
    make_client: ClientFactory = Depends(claude_factory),
):
    """Modo b: el modelo busca el enunciado (Classroom, luego hojas de alumnos) y lo resuelve."""
    _require_model()
    try:
        cw = reader.get_coursework(course_id, coursework_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    a = _assignment(db, teacher, course_id, coursework_id, create=True)
    key = keys.get_or_create(db, a)
    try:
        keys.start_from_teacher(db, key)
    except keys.KeyValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    statement = keys.ClassroomStatement(cw.description, [m.file_id for m in cw.materials])
    background.add_task(keys.run_solve, key.id, statement, source_factory, make_client)
    return _key_out(a, teacher)


class GradingSettings(BaseModel):
    minor_error_factor: float | None = Field(default=None, ge=0, le=1)


@router.put("/grading-settings", response_model=KeyOut)
def put_grading_settings(
    course_id: str,
    coursework_id: str,
    body: GradingSettings,
    teacher: Teacher = Depends(current_teacher),
    db: Session = Depends(get_db),
):
    a = _assignment(db, teacher, course_id, coursework_id, create=True)
    a.minor_error_factor = body.minor_error_factor
    db.commit()
    return _key_out(a, teacher)


@router.post("/submissions/{sid}/grade", status_code=202)
def grade_one(
    course_id: str,
    coursework_id: str,
    sid: str,
    background: BackgroundTasks,
    teacher: Teacher = Depends(current_teacher),
    db: Session = Depends(get_db),
    make_client: ClientFactory = Depends(claude_factory),
):
    sub = _own_submission(db, teacher, coursework_id, sid)
    try:
        grader.check_can_grade(sub)
    except grader.GradingBlocked as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if grader.effective_status(sub) != "con_marca":
        _require_model()
    if sub.grade is not None and sub.grade.status == "calificando":
        return {"started": False}
    grader.mark_as_grading(db, sub)
    background.add_task(grader.grade_submission, sub.id, make_client)
    return {"started": True}
