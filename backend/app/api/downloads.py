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
from app.db.models import Assignment, Page, Submission, Teacher
from app.db.session import get_db
from app.files.base import FileSource
from app.files.drive_readonly import DriveReadonlySource, build_drive_service
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


class SubmissionDownloadOut(BaseModel):
    status: str
    error: str | None
    pages: list[PageOut]


class DownloadStatusOut(BaseModel):
    running: bool
    counts: dict[str, int]
    # clave: id de la entrega en Classroom (el mismo que usa el listado)
    submissions: dict[str, SubmissionDownloadOut]


def _status(assignment: Assignment | None) -> DownloadStatusOut:
    if assignment is None:
        return DownloadStatusOut(running=False, counts={}, submissions={})
    counts: dict[str, int] = {}
    subs = {}
    for s in assignment.submissions:
        counts[s.download_status] = counts.get(s.download_status, 0) + 1
        subs[s.classroom_submission_id] = SubmissionDownloadOut(
            status=s.download_status,
            error=s.error,
            pages=[PageOut(id=p.id, index=p.index, width=p.width, height=p.height) for p in s.pages],
        )
    return DownloadStatusOut(
        running=download.is_running(assignment.id), counts=counts, submissions=subs
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
