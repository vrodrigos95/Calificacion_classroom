from app.classroom.client import ClassroomReader, was_delivered
from tests.conftest import FakeClassroomService

DRIVE_PDF = {"driveFile": {"id": "f1", "title": "tarea.pdf", "alternateLink": "https://drive/f1"}}


def _student(uid, given, family):
    return {
        "userId": uid,
        "profile": {
            "name": {"givenName": given, "familyName": family, "fullName": f"{given} {family}"}
        },
    }


def _sub(sid, uid, state, attachments=None, history=None, late=False):
    return {
        "id": sid,
        "userId": uid,
        "state": state,
        "late": late,
        "alternateLink": f"https://classroom/sub/{sid}",
        "assignmentSubmission": {"attachments": attachments or []},
        "submissionHistory": history or [],
    }


def make_service():
    return FakeClassroomService(
        courses={"me": [{"courses": [{"id": "c1", "name": "Mate 3A", "section": "3A"}]}]},
        coursework={
            "c1": [
                {
                    "courseWork": [
                        {
                            "id": "w1",
                            "title": "Probabilidad",
                            "workType": "ASSIGNMENT",
                            "description": "Resuelve los 4 ejercicios",
                            "dueDate": {"year": 2026, "month": 9, "day": 30},
                            "materials": [
                                {"driveFile": {"driveFile": {"id": "m1", "title": "hoja.pdf"}}},
                                {"link": {"url": "https://example.com"}},
                            ],
                        },
                        {"id": "q1", "title": "Pregunta", "workType": "SHORT_ANSWER_QUESTION"},
                    ]
                },
                {"courseWork": [{"id": "w2", "title": "Conteo"}]},  # segunda página
            ]
        },
        students={
            "c1": [
                {
                    "students": [
                        _student("u1", "Ana", "Zúñiga"),
                        _student("u2", "Beto", "Álvarez"),
                    ]
                },
                {"students": [_student("u3", "Carla", "Méndez"), _student("u4", "Dani", "López")]},
            ]
        },
        submissions={
            "w1": [
                {
                    "studentSubmissions": [
                        _sub("s1", "u1", "TURNED_IN", [DRIVE_PDF], late=True),
                        _sub("s2", "u2", "CREATED"),
                        _sub(
                            "s3",
                            "u3",
                            "RETURNED",
                            [DRIVE_PDF],
                            history=[{"stateHistory": {"state": "TURNED_IN"}}],
                        ),
                        _sub("s4", "u4", "RETURNED"),  # devuelta sin haberla entregado
                        _sub("s5", "u9", "TURNED_IN", [{"link": {"url": "x"}}]),
                    ]
                }
            ]
        },
    )


def test_list_courses_only_active_as_teacher():
    svc = make_service()
    courses = ClassroomReader(svc).list_courses()
    assert [c.name for c in courses] == ["Mate 3A"]
    assert svc.courses_col.calls[0]["teacherId"] == "me"
    assert svc.courses_col.calls[0]["courseStates"] == ["ACTIVE"]


def test_list_coursework_paginates_filters_and_reads_materials():
    works = ClassroomReader(make_service()).list_coursework("c1")
    assert [w.id for w in works] == ["w1", "w2"]
    w1 = works[0]
    assert w1.due_date == "2026-09-30"
    assert [m.file_id for m in w1.materials] == ["m1"]
    assert w1.other_materials == 1


def test_list_submissions_classifies_and_sorts_by_family_name():
    subs = ClassroomReader(make_service()).list_submissions("c1", "w1")
    by_id = {s.id: s for s in subs}

    assert by_id["s1"].status_hint == "entregada" and by_id["s1"].late
    assert by_id["s2"].status_hint == "sin_entrega"
    assert by_id["s3"].status_hint == "entregada"  # RETURNED tras TURNED_IN
    assert by_id["s4"].status_hint == "sin_entrega"  # RETURNED sin entrega previa
    assert by_id["s5"].status_hint == "entregada_sin_archivos"
    assert by_id["s5"].other_attachments == 1
    assert by_id["s5"].student_name == "(alumno fuera del grupo)"

    # Álvarez, López, Méndez, Zúñiga; el alumno desconocido al final.
    assert [s.id for s in subs] == ["s2", "s4", "s3", "s1", "s5"]
    assert by_id["s1"].alternate_link == "https://classroom/sub/s1"


def test_was_delivered_states():
    assert was_delivered({"state": "TURNED_IN"})
    assert not was_delivered({"state": "NEW"})
    assert not was_delivered({"state": "RECLAIMED_BY_STUDENT"})
    assert not was_delivered({"state": "RETURNED", "submissionHistory": []})
