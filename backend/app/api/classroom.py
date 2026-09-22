from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import classroom_reader
from app.classroom.client import ClassroomReader, CourseWork, DriveAttachment

router = APIRouter(prefix="/api/courses", tags=["classroom"])


class CourseOut(BaseModel):
    id: str
    name: str
    section: str
    alternate_link: str


class AttachmentOut(BaseModel):
    file_id: str
    title: str
    alternate_link: str


class CourseWorkOut(BaseModel):
    id: str
    title: str
    description: str
    state: str
    alternate_link: str
    due_date: str | None
    max_points: float | None
    materials: list[AttachmentOut]
    other_materials: int


class SubmissionOut(BaseModel):
    id: str
    user_id: str
    student_name: str
    state: str
    status: str  # entregada | entregada_sin_archivos | sin_entrega
    late: bool
    alternate_link: str
    attachments: list[AttachmentOut]
    other_attachments: int


class SubmissionSummary(BaseModel):
    total: int
    entregadas: int
    sin_archivos: int
    sin_entrega: int


class SubmissionsOut(BaseModel):
    coursework: CourseWorkOut
    summary: SubmissionSummary
    submissions: list[SubmissionOut]


def _att(a: DriveAttachment) -> AttachmentOut:
    return AttachmentOut(file_id=a.file_id, title=a.title, alternate_link=a.alternate_link)


def _cw(cw: CourseWork) -> CourseWorkOut:
    return CourseWorkOut(
        id=cw.id,
        title=cw.title,
        description=cw.description,
        state=cw.state,
        alternate_link=cw.alternate_link,
        due_date=cw.due_date,
        max_points=cw.max_points,
        materials=[_att(m) for m in cw.materials],
        other_materials=cw.other_materials,
    )


@router.get("", response_model=list[CourseOut])
def list_courses(reader: ClassroomReader = Depends(classroom_reader)):
    return [CourseOut(**vars(c)) for c in reader.list_courses()]


@router.get("/{course_id}/coursework", response_model=list[CourseWorkOut])
def list_coursework(course_id: str, reader: ClassroomReader = Depends(classroom_reader)):
    return [_cw(cw) for cw in reader.list_coursework(course_id)]


@router.get("/{course_id}/coursework/{coursework_id}/submissions", response_model=SubmissionsOut)
def list_submissions(
    course_id: str, coursework_id: str, reader: ClassroomReader = Depends(classroom_reader)
):
    try:
        cw = reader.get_coursework(course_id, coursework_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    subs = reader.list_submissions(course_id, coursework_id)
    out = [
        SubmissionOut(
            id=s.id,
            user_id=s.user_id,
            student_name=s.student_name,
            state=s.state,
            status=s.status_hint,
            late=s.late,
            alternate_link=s.alternate_link,
            attachments=[_att(a) for a in s.attachments],
            other_attachments=s.other_attachments,
        )
        for s in subs
    ]
    summary = SubmissionSummary(
        total=len(out),
        entregadas=sum(o.status == "entregada" for o in out),
        sin_archivos=sum(o.status == "entregada_sin_archivos" for o in out),
        sin_entrega=sum(o.status == "sin_entrega" for o in out),
    )
    return SubmissionsOut(coursework=_cw(cw), summary=summary, submissions=out)
