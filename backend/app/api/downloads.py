import json
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.answer_key.service import key_state
from app.api.deps import classroom_reader, current_teacher
from app.auth.google_oauth import credentials_for
from app.classroom.client import ClassroomReader
from app.config import get_settings
from app.db.models import MK_CON_MARCA, MODE_SOLO_FIRMA, V_DUDOSA, V_MARCA, Assignment, Page, Submission, Teacher
from app.db.session import get_db
from app.files.base import FileSource
from app.files.drive_readonly import DriveReadonlySource, build_drive_service
from app.marks import service as mark_service
from app.pipeline import batch, download

router = APIRouter(prefix="/api", tags=["descargas"])

SourceFactory = Callable[[], FileSource]


def file_source_factory(
    teacher: Teacher = Depends(current_teacher), db: Session = Depends(get_db)
) -> SourceFactory:
    """Fuente de archivos del docente. Aquí se cambia Drive por ZIP o Picker más adelante."""
    creds = credentials_for(db, teacher.id)
    return lambda: DriveReadonlySource(build_drive_service(creds))


class PageOut(BaseModel):
    id: int
    index: int
    width: int
    height: int


class DetectionOut(BaseModel):
    id: int
    mark_name: str
    meaning: str
    verdict: str  # marca | dudosa
    confidence: float
    reason: str
    verifier: str
    page_index: int


class GradeOut(BaseModel):
    status: str  # calificando | revisada | revisar_a_mano | con_marca | error
    score: float | None
    comment: str | None
    review_reasons: list[str]
    exercises: list[dict]
    error: str | None
    stale: bool  # se calificó con una versión anterior de la clave


class SubmissionDownloadOut(BaseModel):
    status: str
    error: str | None
    pages: list[PageOut]
    # Módulo de marca (etapa 3)
    mark_status: str | None  # ya considera la decisión del docente
    mark_detail: str | None
    mark_confirmed: bool | None
    detections: list[DetectionOut]  # solo marcas y dudosas, con su recorte
    suggested_score: float | None  # 100 si tiene marca "tarea correcta"; si no, la de la calificación
    grade: GradeOut | None
    # Panel (etapa 5)
    panel_status: str  # sin_entrega | pendiente | procesando | con_marca | revisada | revisar_a_mano | error
    panel_note: str | None
    final_score: float | None  # la del docente si la ajustó; si no, la sugerida
    final_comment: str
    suggested_comment: str  # el automático (de la calificación o del modo «solo firma»)
    score_override: float | None
    comment_override: str | None
    captured: bool


class DownloadStatusOut(BaseModel):
    grading_mode: str
    batch_running: bool
    batch_phase: str | None
    batch_note: str | None
    running: bool
    marks_running: bool
    grading_running: bool
    key_state: str
    mark_module_enabled: bool
    counts: dict[str, int]
    # clave: id de la entrega en Classroom (el mismo que usa el listado)
    submissions: dict[str, SubmissionDownloadOut]


def _grade_out(s: Submission) -> GradeOut | None:
    g = s.grade
    if g is None:
        return None
    key = s.assignment.answer_key
    return GradeOut(
        status=g.status,
        score=g.score,
        comment=g.comment,
        review_reasons=(g.review_reasons or "").splitlines(),
        exercises=json.loads(g.detail_json or "[]"),
        error=g.error,
        stale=bool(key and g.key_version is not None and g.key_version != key.version and g.status != "con_marca"),
    )


def _panel_status(s: Submission, mark_status: str | None, grade: GradeOut | None) -> tuple[str, str | None]:
    """Estado único para el panel, con una nota breve de por qué."""
    if not s.delivered:
        return "sin_entrega", None
    if s.download_status == "error":
        return "error", s.error
    if grade is not None and grade.status == "calificando":
        return "procesando", None
    if s.download_status in ("pendiente", "descargando"):
        return "procesando" if s.download_status == "descargando" else "pendiente", None
    if mark_status == MK_CON_MARCA:
        return "con_marca", None
    if mark_status in ("dudosa", "error") and s.mark_confirmed is None:
        return "revisar_a_mano", s.mark_detail or "Posible marca por confirmar"
    if grade is None or grade.stale:
        return "pendiente", "Se calificó con otra versión de la clave" if grade else None
    if grade.status == "error":
        return "error", grade.error
    if grade.status == "revisar_a_mano":
        return "revisar_a_mano", "; ".join(grade.review_reasons) or None
    if grade.status == "revisada":
        return "revisada", None
    return "pendiente", None


def _signature_only(s: Submission, mark_status: str | None) -> tuple[str, str | None, float | None, str]:
    """Modo «solo revisar firma»: con firma = 100; sin firma = puntaje y comentario de la tarea.

    Devuelve (estado del panel, nota, calificación sugerida, comentario sugerido).
    Una marca dudosa no tiene calificación sugerida: el docente debe decidir primero.
    """
    a = s.assignment
    if not s.delivered:
        return "sin_entrega", None, None, ""
    if s.download_status == "error":
        return "error", s.error, None, ""
    if s.download_status in ("pendiente", "descargando"):
        return ("procesando" if s.download_status == "descargando" else "pendiente"), None, None, ""
    if mark_status == MK_CON_MARCA:
        return "con_marca", None, 100.0, ""
    if mark_status in ("dudosa", "error"):
        return "revisar_a_mano", "¿Es tu firma? Confírmala (100) o recházala", None, ""
    if mark_status == "sin_marca":
        note = "Rechazaste la marca" if s.mark_confirmed is False else "No se encontró tu firma; si sí la tiene, revisa la hoja"
        return "sin_firma", note, a.unsigned_score, a.unsigned_comment
    notes = {
        None: "Falta buscar la firma: da clic en «Procesar tarea»",
        "desactivado": "Activa «Buscar mi marca en esta tarea» para este modo",
        "sin_config": "Configura tu marca en «Mi marca»",
        "no_revisable": "La entrega no tiene imágenes",
    }
    return ("error" if mark_status == "no_revisable" else "pendiente"), notes.get(mark_status), None, ""


def _submission_out(s: Submission) -> SubmissionDownloadOut:
    mark_status = mark_service.effective_status(s)
    grade = _grade_out(s)
    if s.assignment.grading_mode == MODE_SOLO_FIRMA:
        panel_status, panel_note, suggested, auto_comment = _signature_only(s, mark_status)
    else:
        if mark_status == MK_CON_MARCA:
            suggested = 100.0
        elif grade and grade.status in ("revisada", "revisar_a_mano") and not grade.stale:
            suggested = grade.score
        else:
            suggested = None
        panel_status, panel_note = _panel_status(s, mark_status, grade)
        # Con marca "tarea correcta" el contenido no se revisa: no aplica el comentario de ejercicios.
        auto_comment = "" if mark_status == MK_CON_MARCA else (grade.comment if grade and not grade.stale else "")
    final_comment = s.comment_override if s.comment_override is not None else auto_comment
    return SubmissionDownloadOut(
        panel_status=panel_status,
        panel_note=panel_note,
        final_score=s.score_override if s.score_override is not None else suggested,
        final_comment=final_comment or "",
        suggested_comment=auto_comment or "",
        score_override=s.score_override,
        comment_override=s.comment_override,
        captured=s.captured,
        status=s.download_status,
        error=s.error,
        pages=[PageOut(id=p.id, index=p.index, width=p.width, height=p.height) for p in s.pages],
        mark_status=mark_status,
        mark_detail=s.mark_detail,
        mark_confirmed=s.mark_confirmed,
        detections=[
            DetectionOut(
                id=d.id,
                mark_name=d.mark.name if d.mark else "(marca borrada)",
                meaning=d.mark.meaning if d.mark else "informativa",
                verdict=d.verdict,
                confidence=d.confidence,
                reason=d.reason,
                verifier=d.verifier,
                page_index=d.page_index,
            )
            for d in s.detections
            if d.verdict in (V_MARCA, V_DUDOSA)
        ],
        suggested_score=suggested,
        grade=grade,
    )


def _status(assignment: Assignment | None) -> DownloadStatusOut:
    if assignment is None:
        return DownloadStatusOut(
            grading_mode="ejercicios",
            batch_running=False,
            batch_phase=None,
            batch_note=None,
            running=False,
            marks_running=False,
            grading_running=False,
            key_state="sin_clave",
            mark_module_enabled=True,
            counts={},
            submissions={},
        )
    counts: dict[str, int] = {}
    subs = {}
    for s in assignment.submissions:
        counts[s.download_status] = counts.get(s.download_status, 0) + 1
        subs[s.classroom_submission_id] = _submission_out(s)
    bs = batch.state(assignment.id)
    return DownloadStatusOut(
        grading_mode=assignment.grading_mode,
        batch_running=batch.is_running(assignment.id),
        batch_phase=bs.phase if bs else None,
        batch_note=bs.note if bs else None,
        running=download.is_running(assignment.id),
        marks_running=mark_service.is_running(assignment.id),
        grading_running=any(s.grade is not None and s.grade.status == "calificando" for s in assignment.submissions),
        key_state=key_state(assignment.answer_key),
        mark_module_enabled=assignment.mark_module_enabled,
        counts=counts,
        submissions=subs,
    )


def _assignment(db: Session, teacher: Teacher, coursework_id: str) -> Assignment | None:
    return (
        db.query(Assignment).filter_by(teacher_id=teacher.id, coursework_id=coursework_id).one_or_none()
    )


@router.get(
    "/courses/{course_id}/coursework/{coursework_id}/download", response_model=DownloadStatusOut
)
def download_status(
    course_id: str,
    coursework_id: str,
    teacher: Teacher = Depends(current_teacher),
    db: Session = Depends(get_db),
):
    return _status(_assignment(db, teacher, coursework_id))


@router.post(
    "/courses/{course_id}/coursework/{coursework_id}/download", response_model=DownloadStatusOut
)
def start_download(
    course_id: str,
    coursework_id: str,
    background: BackgroundTasks,
    teacher: Teacher = Depends(current_teacher),
    db: Session = Depends(get_db),
    reader: ClassroomReader = Depends(classroom_reader),
    source_factory: SourceFactory = Depends(file_source_factory),
):
    """Sincroniza con Classroom y descarga las entregas nuevas, cambiadas o con error."""
    try:
        assignment = download.sync_submissions(db, teacher.id, reader, course_id, coursework_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    download.queue_retry_errors(db, assignment)
    if download.try_claim(assignment.id):
        background.add_task(download.run_downloads, assignment.id, source_factory)
    db.refresh(assignment)
    return _status(assignment)


@router.get("/pages/{page_id}")
def page_image(
    page_id: int, teacher: Teacher = Depends(current_teacher), db: Session = Depends(get_db)
):
    page = (
        db.query(Page)
        .join(Submission)
        .join(Assignment)
        .filter(Page.id == page_id, Assignment.teacher_id == teacher.id)
        .one_or_none()
    )
    if page is None:
        raise HTTPException(status_code=404, detail="Página no encontrada")
    path = Path(get_settings().data_dir) / page.path
    if not path.is_file():
        raise HTTPException(status_code=410, detail="La imagen ya se borró por retención")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})
