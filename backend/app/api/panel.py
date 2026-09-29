from collections.abc import Callable

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import classroom_reader, current_teacher
from app.api.downloads import SourceFactory, file_source_factory
from app.api.grading import ClientFactory, claude_factory
from app.api.marks import _own_submission, verifier_factory
from app.classroom.client import ClassroomReader
from app.db.models import Teacher
from app.db.session import get_db
from app.marks.verifier import Verifier
from app.pipeline import batch, download

router = APIRouter(prefix="/api/courses/{course_id}/coursework/{coursework_id}", tags=["panel"])


@router.post("/process", status_code=202)
def process_assignment(
    course_id: str,
    coursework_id: str,
    background: BackgroundTasks,
    teacher: Teacher = Depends(current_teacher),
    db: Session = Depends(get_db),
    reader: ClassroomReader = Depends(classroom_reader),
    source_factory: SourceFactory = Depends(file_source_factory),
    make_verifier: Callable[[], Verifier] = Depends(verifier_factory),
    make_client: ClientFactory = Depends(claude_factory),
):
    """Un clic: sincroniza con Classroom, descarga, busca marcas y califica."""
    try:
        a = download.sync_submissions(db, teacher.id, reader, course_id, coursework_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    download.queue_retry_errors(db, a)
    if not batch.try_claim(a.id):
        return {"started": False}
    background.add_task(batch.run_all, a.id, source_factory, make_verifier, make_client)
    return {"started": True}


class ReviewIn(BaseModel):
    """Solo se cambian los campos que se envían; null borra el ajuste."""

    captured: bool | None = None
    score_override: float | None = Field(default=None, ge=0, le=100)
    comment_override: str | None = Field(default=None, max_length=5000)


@router.patch("/submissions/{sid}/review")
def review_submission(
    course_id: str,
    coursework_id: str,
    sid: str,
    body: ReviewIn,
    teacher: Teacher = Depends(current_teacher),
    db: Session = Depends(get_db),
):
    sub = _own_submission(db, teacher, coursework_id, sid)
    data = body.model_dump(exclude_unset=True)
    if "captured" in data:
        sub.captured = bool(data["captured"])
    if "score_override" in data:
        sub.score_override = data["score_override"]
    if "comment_override" in data:
        sub.comment_override = data["comment_override"]
    db.commit()
    return {"ok": True}
