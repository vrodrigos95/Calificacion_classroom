from collections.abc import Callable
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_teacher
from app.config import get_settings
from app.db.models import (
    MK_DUDOSA,
    MK_ERROR,
    Assignment,
    MarkDetection,
    MarkReference,
    Submission,
    Teacher,
    ValidationMark,
)
from app.db.session import get_db
from app.marks import service
from app.marks.verifier import Verifier, default_verifier

router = APIRouter(prefix="/api", tags=["marcas"])

Meaning = Literal["correcta", "informativa"]
Zone = Literal["primera", "cualquiera"]


def verifier_factory() -> Callable[[], Verifier]:
    return default_verifier


# ---- Configuración de marcas -----------------------------------------------------------

class ReferenceOut(BaseModel):
    id: int
    url: str


class MarkOut(BaseModel):
    id: int
    name: str
    meaning: Meaning
    zone: Zone
    active: bool
    colored: bool
    references: list[ReferenceOut]


class MarksConfigOut(BaseModel):
    verifier: Literal["claude", "local"]
    model: str | None
    marks: list[MarkOut]


def _mark_out(m: ValidationMark) -> MarkOut:
    return MarkOut(
        id=m.id,
        name=m.name,
        meaning=m.meaning,
        zone=m.zone,
        active=m.active,
        colored=service.profile_of(m).colored,
        references=[ReferenceOut(id=r.id, url=f"/api/marks/{m.id}/references/{r.id}") for r in m.references],
    )


def _own_mark(db: Session, teacher: Teacher, mark_id: int) -> ValidationMark:
    mark = db.get(ValidationMark, mark_id)
    if mark is None or mark.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="Marca no encontrada")
    return mark


@router.get("/marks", response_model=MarksConfigOut)
def list_marks(teacher: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    has_key = bool(get_settings().anthropic_api_key)
    marks = db.query(ValidationMark).filter_by(teacher_id=teacher.id).order_by(ValidationMark.id)
    return MarksConfigOut(
        verifier="claude" if has_key else "local",
        model=get_settings().claude_model if has_key else None,
        marks=[_mark_out(m) for m in marks],
    )


async def _read_files(files: list[UploadFile]) -> list[bytes]:
    return [await f.read() for f in files]


@router.post("/marks", response_model=MarkOut)
async def create_mark(
    name: str = Form(...),
    meaning: Meaning = Form("correcta"),
    zone: Zone = Form("primera"),
    files: list[UploadFile] = File(...),
    teacher: Teacher = Depends(current_teacher),
    db: Session = Depends(get_db),
):
    try:
        mark = service.create_mark(db, teacher, name, meaning, zone, await _read_files(files))
    except service.MarkConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _mark_out(mark)


class MarkPatch(BaseModel):
    name: str | None = None
    meaning: Meaning | None = None
    zone: Zone | None = None
    active: bool | None = None


@router.patch("/marks/{mark_id}", response_model=MarkOut)
def update_mark(
    mark_id: int, patch: MarkPatch, teacher: Teacher = Depends(current_teacher), db: Session = Depends(get_db)
):
    mark = _own_mark(db, teacher, mark_id)
    for field, value in patch.model_dump(exclude_none=True).items():
        setattr(mark, field, value.strip() if isinstance(value, str) and field == "name" else value)
    db.commit()
    return _mark_out(mark)


@router.put("/marks/{mark_id}/references", response_model=MarkOut)
async def replace_references(
    mark_id: int,
    files: list[UploadFile] = File(...),
    teacher: Teacher = Depends(current_teacher),
    db: Session = Depends(get_db),
):
    mark = _own_mark(db, teacher, mark_id)
    try:
        service.set_references(db, mark, await _read_files(files))
    except service.MarkConfigError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return _mark_out(mark)


@router.delete("/marks/{mark_id}", status_code=204)
def delete_mark(mark_id: int, teacher: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    service.delete_mark(db, _own_mark(db, teacher, mark_id))


@router.get("/marks/{mark_id}/references/{ref_id}")
def reference_image(
    mark_id: int, ref_id: int, teacher: Teacher = Depends(current_teacher), db: Session = Depends(get_db)
):
    mark = _own_mark(db, teacher, mark_id)
    ref = db.get(MarkReference, ref_id)
    if ref is None or ref.mark_id != mark.id:
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    return FileResponse(Path(get_settings().data_dir) / ref.path, media_type="image/png")


# ---- Por tarea --------------------------------------------------------------------------

def _assignment(db: Session, teacher: Teacher, course_id: str, coursework_id: str, create: bool = False):
    a = db.query(Assignment).filter_by(teacher_id=teacher.id, coursework_id=coursework_id).one_or_none()
    if a is None and create:
        a = Assignment(teacher_id=teacher.id, course_id=course_id, coursework_id=coursework_id)
        db.add(a)
        db.commit()
    return a


class AssignmentSettings(BaseModel):
    mark_module_enabled: bool


@router.get("/courses/{course_id}/coursework/{coursework_id}/settings", response_model=AssignmentSettings)
def get_assignment_settings(
    course_id: str, coursework_id: str, teacher: Teacher = Depends(current_teacher), db: Session = Depends(get_db)
):
    a = _assignment(db, teacher, course_id, coursework_id)
    return AssignmentSettings(mark_module_enabled=a.mark_module_enabled if a else True)


@router.put("/courses/{course_id}/coursework/{coursework_id}/settings", response_model=AssignmentSettings)
def put_assignment_settings(
    course_id: str,
    coursework_id: str,
    body: AssignmentSettings,
    teacher: Teacher = Depends(current_teacher),
    db: Session = Depends(get_db),
):
    a = _assignment(db, teacher, course_id, coursework_id, create=True)
    a.mark_module_enabled = body.mark_module_enabled
    db.commit()
    return AssignmentSettings(mark_module_enabled=a.mark_module_enabled)


@router.post("/courses/{course_id}/coursework/{coursework_id}/marks/detect", status_code=202)
def detect_marks(
    course_id: str,
    coursework_id: str,
    background: BackgroundTasks,
    teacher: Teacher = Depends(current_teacher),
    db: Session = Depends(get_db),
    make_verifier: Callable[[], Verifier] = Depends(verifier_factory),
):
    a = _assignment(db, teacher, course_id, coursework_id)
    if a is None:
        raise HTTPException(status_code=409, detail="Primero descarga las entregas")
    started = service.try_claim(a.id)
    if started:
        background.add_task(service.run_mark_detection, a.id, make_verifier)
    return {"started": started}


def _own_submission(db: Session, teacher: Teacher, coursework_id: str, classroom_sid: str) -> Submission:
    sub = (
        db.query(Submission)
        .join(Assignment)
        .filter(
            Assignment.teacher_id == teacher.id,
            Assignment.coursework_id == coursework_id,
            Submission.classroom_submission_id == classroom_sid,
        )
        .one_or_none()
    )
    if sub is None:
        raise HTTPException(status_code=404, detail="Entrega no encontrada")
    return sub


class Decision(BaseModel):
    confirmed: bool | None  # True = sí es mi marca, False = no lo es, None = deshacer


@router.put("/courses/{course_id}/coursework/{coursework_id}/submissions/{sid}/mark-decision")
def mark_decision(
    course_id: str,
    coursework_id: str,
    sid: str,
    body: Decision,
    teacher: Teacher = Depends(current_teacher),
    db: Session = Depends(get_db),
):
    sub = _own_submission(db, teacher, coursework_id, sid)
    if body.confirmed is True and not sub.detections:
        raise HTTPException(status_code=409, detail="No hay recorte de marca que confirmar")
    sub.mark_confirmed = body.confirmed
    db.commit()
    return {"mark_status": service.effective_status(sub)}


@router.post("/courses/{course_id}/coursework/{coursework_id}/marks/confirm-all")
def confirm_all(
    course_id: str, coursework_id: str, teacher: Teacher = Depends(current_teacher), db: Session = Depends(get_db)
):
    """Confirma todas las marcas dudosas o sin verificar que tienen recorte (el docente ya las vio)."""
    a = _assignment(db, teacher, course_id, coursework_id)
    n = 0
    for sub in a.submissions if a else []:
        if sub.mark_confirmed is None and sub.mark_status in (MK_DUDOSA, MK_ERROR) and sub.detections:
            sub.mark_confirmed = True
            n += 1
    db.commit()
    return {"confirmed": n}


@router.get("/detections/{det_id}/crop")
def detection_crop(det_id: int, teacher: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    det = (
        db.query(MarkDetection)
        .join(Submission)
        .join(Assignment)
        .filter(MarkDetection.id == det_id, Assignment.teacher_id == teacher.id)
        .one_or_none()
    )
    if det is None:
        raise HTTPException(status_code=404, detail="Recorte no encontrado")
    path = Path(get_settings().data_dir) / det.crop_path
    if not path.is_file():
        raise HTTPException(status_code=410, detail="El recorte ya se borró por retención")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})

