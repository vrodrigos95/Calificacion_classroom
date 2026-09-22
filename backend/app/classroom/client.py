"""Lectura de Google Classroom. Esta app nunca escribe en Classroom.

`ClassroomReader` recibe un servicio de googleapiclient ya construido, para poder
probarlo con un servicio falso.
"""

import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterator

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Estados de entrega de la API de Classroom
TURNED_IN = "TURNED_IN"
RETURNED = "RETURNED"


@dataclass
class Course:
    id: str
    name: str
    section: str
    alternate_link: str


@dataclass
class DriveAttachment:
    file_id: str
    title: str
    alternate_link: str


@dataclass
class CourseWork:
    id: str
    title: str
    description: str
    state: str
    alternate_link: str
    due_date: str | None
    max_points: float | None
    materials: list[DriveAttachment] = field(default_factory=list)
    other_materials: int = 0


@dataclass
class Submission:
    id: str
    user_id: str
    student_name: str
    student_sort_key: str
    state: str
    delivered: bool
    late: bool
    alternate_link: str
    attachments: list[DriveAttachment] = field(default_factory=list)
    other_attachments: int = 0  # enlaces, formularios, videos: no se pueden calificar

    @property
    def status_hint(self) -> str:
        if not self.delivered:
            return "sin_entrega"
        if not self.attachments:
            return "entregada_sin_archivos"
        return "entregada"


def build_service(credentials: Credentials):
    # httplib2 no es thread-safe: se construye un servicio por petición.
    return build("classroom", "v1", credentials=credentials, cache_discovery=False)


def _paginate(request_factory, key: str) -> Iterator[dict]:
    token = None
    while True:
        resp = request_factory(token).execute()
        yield from resp.get(key, [])
        token = resp.get("nextPageToken")
        if not token:
            return


def _drive_attachments(items: list[dict]) -> tuple[list[DriveAttachment], int]:
    files, other = [], 0
    for item in items or []:
        df = item.get("driveFile")
        if df and "driveFile" in df:  # materiales anidan como {"driveFile": {"driveFile": {...}}}
            df = df["driveFile"]
        if df and df.get("id"):
            files.append(
                DriveAttachment(
                    file_id=df["id"],
                    title=df.get("title", ""),
                    alternate_link=df.get("alternateLink", ""),
                )
            )
        else:
            other += 1
    return files, other


def _sort_key(text: str) -> str:
    """Orden alfabético sin distinguir acentos ni mayúsculas (Álvarez antes que Zúñiga)."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def _format_due(cw: dict) -> str | None:
    d = cw.get("dueDate")
    if not d:
        return None
    return f"{d.get('year', 0):04d}-{d.get('month', 0):02d}-{d.get('day', 0):02d}"


def was_delivered(sub: dict) -> bool:
    """TURNED_IN, o RETURNED con un TURNED_IN previo en el historial.

    Un docente puede devolver una tarea que el alumno nunca entregó; eso no cuenta.
    """
    state = sub.get("state")
    if state == TURNED_IN:
        return True
    if state == RETURNED:
        for h in sub.get("submissionHistory", []) or []:
            if h.get("stateHistory", {}).get("state") == TURNED_IN:
                return True
    return False


class ClassroomReader:
    def __init__(self, service: Any):
        self.svc = service

    def list_courses(self) -> list[Course]:
        courses = _paginate(
            lambda t: self.svc.courses().list(
                teacherId="me", courseStates=["ACTIVE"], pageToken=t, pageSize=100
            ),
            "courses",
        )
        return [
            Course(
                id=c["id"],
                name=c.get("name", ""),
                section=c.get("section", ""),
                alternate_link=c.get("alternateLink", ""),
            )
            for c in courses
        ]

    def list_coursework(self, course_id: str) -> list[CourseWork]:
        items = _paginate(
            lambda t: self.svc.courses()
            .courseWork()
            .list(courseId=course_id, orderBy="updateTime desc", pageToken=t, pageSize=100),
            "courseWork",
        )
        result = []
        for cw in items:
            if cw.get("workType", "ASSIGNMENT") != "ASSIGNMENT":
                continue  # preguntas y cuestionarios no llevan hojas manuscritas
            materials, other = _drive_attachments(cw.get("materials", []))
            result.append(
                CourseWork(
                    id=cw["id"],
                    title=cw.get("title", ""),
                    description=cw.get("description", ""),
                    state=cw.get("state", ""),
                    alternate_link=cw.get("alternateLink", ""),
                    due_date=_format_due(cw),
                    max_points=cw.get("maxPoints"),
                    materials=materials,
                    other_materials=other,
                )
            )
        return result

    def get_coursework(self, course_id: str, coursework_id: str) -> CourseWork:
        for cw in self.list_coursework(course_id):
            if cw.id == coursework_id:
                return cw
        raise KeyError(coursework_id)

    def _roster(self, course_id: str) -> dict[str, tuple[str, str]]:
        """userId -> (nombre completo, clave de orden por apellido)."""
        students = _paginate(
            lambda t: self.svc.courses()
            .students()
            .list(courseId=course_id, pageToken=t, pageSize=100),
            "students",
        )
        roster = {}
        for st in students:
            name = st.get("profile", {}).get("name", {})
            full = name.get("fullName") or " ".join(
                x for x in (name.get("givenName"), name.get("familyName")) if x
            )
            sort_key = f"{name.get('familyName', '')} {name.get('givenName', '')}".strip()
            roster[st["userId"]] = (full, _sort_key(sort_key or full))
        return roster

    def list_submissions(self, course_id: str, coursework_id: str) -> list[Submission]:
        """Todas las entregas del trabajo (incluye alumnos sin entrega), ordenadas por apellido."""
        roster = self._roster(course_id)
        subs = _paginate(
            lambda t: self.svc.courses()
            .courseWork()
            .studentSubmissions()
            .list(courseId=course_id, courseWorkId=coursework_id, pageToken=t, pageSize=100),
            "studentSubmissions",
        )
        result = []
        for s in subs:
            user_id = s.get("userId", "")
            name, sort_key = roster.get(user_id, ("(alumno fuera del grupo)", "~"))
            attachments, other = _drive_attachments(
                s.get("assignmentSubmission", {}).get("attachments", [])
            )
            result.append(
                Submission(
                    id=s["id"],
                    user_id=user_id,
                    student_name=name,
                    student_sort_key=sort_key,
                    state=s.get("state", ""),
                    delivered=was_delivered(s),
                    late=bool(s.get("late")),
                    alternate_link=s.get("alternateLink", ""),
                    attachments=attachments,
                    other_attachments=other,
                )
            )
        # Classroom crea una submission (NEW/CREATED) por cada alumno asignado, así que los
        # alumnos sin entrega ya vienen aquí; los no asignados a la tarea no aparecen.
        result.sort(key=lambda x: x.student_sort_key)
        return result
