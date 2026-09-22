"""Construye el servicio real (discovery estático, sin red) y valida URLs y parámetros."""

from google.auth.credentials import AnonymousCredentials

from app.classroom.client import build_service


def test_requests_match_real_classroom_api():
    svc = build_service(AnonymousCredentials())
    req = svc.courses().list(teacherId="me", courseStates=["ACTIVE"], pageSize=100)
    assert "/v1/courses?" in req.uri and "teacherId=me" in req.uri and "courseStates=ACTIVE" in req.uri

    req = svc.courses().courseWork().list(courseId="c1", orderBy="updateTime desc", pageSize=100)
    assert "/v1/courses/c1/courseWork?" in req.uri

    req = svc.courses().students().list(courseId="c1", pageSize=100)
    assert "/v1/courses/c1/students?" in req.uri

    req = svc.courses().courseWork().studentSubmissions().list(
        courseId="c1", courseWorkId="w1", pageSize=100
    )
    assert "/v1/courses/c1/courseWork/w1/studentSubmissions?" in req.uri
    assert req.method == "GET"
