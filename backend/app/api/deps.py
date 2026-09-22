from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.google_oauth import credentials_for
from app.classroom.client import ClassroomReader, build_service
from app.db.models import Teacher
from app.db.session import get_db


def current_teacher(request: Request, db: Session = Depends(get_db)) -> Teacher:
    teacher_id = request.session.get("teacher_id")
    teacher = db.get(Teacher, teacher_id) if teacher_id else None
    if teacher is None:
        raise HTTPException(status_code=401, detail="No has iniciado sesión")
    return teacher


def classroom_reader(
    teacher: Teacher = Depends(current_teacher), db: Session = Depends(get_db)
) -> ClassroomReader:
    return ClassroomReader(build_service(credentials_for(db, teacher.id)))
