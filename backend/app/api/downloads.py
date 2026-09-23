from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import classroom_reader, current_teacher
from app.auth.google_oauth import credentials_for
from app.classroom.client import ClassroomReader
from app.config import get_settings
from app.db.models import MK_CON_MARCA, V_DUDOSA, V_MARCA, Assignment, Page, Submission, Teacher
from app.db.session import get_db
from app.files.base import FileSource
from app.files.drive_readonly import DriveReadonlySource, build_drive_service
from app.marks import service as mark_service
from app.pipeline import download

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


class SubmissionDownloadOut(BaseModel):
    status: str
    error: str | None
    pages: list[PageOut]
    # Módulo de marca (etapa 3)
    mark_status: str | None  # ya considera la decisión del docente
    mark_detail: str | None
    mark_confirmed: bool | None
    detections: list[DetectionOut]  # solo marcas y dudosas, con su recorte
    suggested_score: float | None  # 100 si tiene marca "tarea correcta"


class DownloadStatusOut(BaseModel):
    running: bool
    marks_running: bool
    mark_module_enabled: bool
    counts: dict[str, int]
    # clave: id de la entrega en Classroom (el mismo que usa el listado)
    submissions: dict[str, SubmissionDownloadOut]


def _submission_out(s: Submission) -> SubmissionDownloadOut:
    mark_status = mark_service.effective_status(s)
    return SubmissionDownloadOut(
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
        suggested_score=100.0 if mark_status == MK_CON_MARCA else None,
    )


def _status(assignment: Assignment | None) -> DownloadStatusOut:
    if assignment is None:
        return DownloadStatusOut(
            running=False, marks_running=False, mark_module_enabled=True, counts={}, submissions={}
        )
    counts: dict[str, int] = {}
    subs = {}
    for s in assignment.submissions:
        counts[s.download_status] = counts.get(s.download_status, 0) + 1
        subs[s.classroom_submission_id] = _submission_out(s)
    return DownloadStatusOut(
        running=download.is_running(assignment.id),
        marks_running=mark_service.is_running(assignment.id),
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
