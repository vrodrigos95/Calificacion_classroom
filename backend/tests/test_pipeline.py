import io
import logging
from datetime import timedelta
from pathlib import Path

from app.classroom.client import ClassroomReader
from app.config import get_settings
from app.db.models import Assignment, Submission, Teacher, TeacherSettings, utcnow
from app.db.session import SessionLocal
from app.files.base import FetchedFile, FileFetchError
from app.logging_conf import build_handler
from app.pipeline import download
from app.retention.cleanup import purge_expired_images
from tests.conftest import FakeClassroomService
from tests.helpers import jpeg_bytes, pdf_bytes, sheet_image


def _att(fid):
    return {"driveFile": {"id": fid, "title": f"{fid}.pdf"}}


def _sub(sid, uid, state, files=()):
    return {
        "id": sid,
        "userId": uid,
        "state": state,
        "alternateLink": f"https://classroom/{sid}",
        "assignmentSubmission": {"attachments": [_att(f) for f in files]},
    }


def reader(submissions):
    students = [
        {"userId": f"u{i}", "profile": {"name": {"givenName": f"A{i}", "familyName": f"B{i}", "fullName": f"A{i} B{i}"}}}
        for i in range(1, 7)
    ]
    return ClassroomReader(
        FakeClassroomService(
            coursework={"c1": [{"courseWork": [{"id": "w1", "title": "Probabilidad"}]}]},
            students={"c1": [{"students": students}]},
            submissions={"w1": [{"studentSubmissions": submissions}]},
        )
    )


class FakeSource:
    def __init__(self, files):
        self.files = files
        self.calls = []

    def fetch(self, file_id):
        self.calls.append(file_id)
        item = self.files[file_id]
        if isinstance(item, Exception):
            raise item
        mime, data = item
        return FetchedFile(file_id, file_id, mime, data)


def _teacher(db):
    t = Teacher(google_sub="s", email="d@x", name="D", settings=TeacherSettings())
    db.add(t)
    db.commit()
    return t


FILES = {
    "pdf2": ("application/pdf", pdf_bytes(2)),
    "foto": ("image/jpeg", jpeg_bytes(sheet_image())),
    "roto": ("application/pdf", b"%PDF-1.4 basura"),
    "borrado": FileFetchError("El archivo ya no existe en Drive"),
    "explota": RuntimeError("fallo raro con el archivo de A5 B5"),
}

SUBS = [
    _sub("s1", "u1", "TURNED_IN", ["pdf2", "foto"]),  # 2 archivos -> 3 páginas
    _sub("s2", "u2", "TURNED_IN", ["roto"]),
    _sub("s3", "u3", "TURNED_IN", ["borrado"]),
    _sub("s4", "u4", "CREATED"),
    _sub("s5", "u5", "TURNED_IN", ["explota"]),
    _sub("s6", "u6", "TURNED_IN", []),
]


def _run(db, teacher, subs, source):
    a = download.sync_submissions(db, teacher.id, reader(subs), "c1", "w1")
    download.queue_retry_errors(db, a)
    assert download.try_claim(a.id)
    download.run_downloads(a.id, lambda: source)
    db.expire_all()
    return {s.classroom_submission_id: s for s in db.get(Assignment, a.id).submissions}


def test_one_failure_does_not_stop_the_rest():
    stream = io.StringIO()
    handler = build_handler(stream)
    logging.getLogger().addHandler(handler)
    try:
        _check_isolation()
    finally:
        logging.getLogger().removeHandler(handler)
    # Cero datos de alumnos en logs, ni siquiera dentro de un traceback.
    text = stream.getvalue()
    assert "Error inesperado al descargar la entrega" in text and "Traceback" in text
    assert "A5 B5" not in text and "[alumno]" in text


def _check_isolation():
    with SessionLocal() as db:
        t = _teacher(db)
        subs = _run(db, t, SUBS, FakeSource(FILES))

        assert subs["s1"].download_status == "lista"
        assert [p.index for p in subs["s1"].pages] == [0, 1, 2]
        assert subs["s1"].pages[2].source_file_id == "foto"
        for p in subs["s1"].pages:
            assert (Path(get_settings().data_dir) / p.path).read_bytes()[:2] == b"\xff\xd8"

        assert subs["s2"].download_status == "error" and "PDF dañado" in subs["s2"].error
        assert subs["s3"].download_status == "error" and "ya no existe" in subs["s3"].error
        assert subs["s4"].download_status == "sin_entrega"
        assert subs["s5"].download_status == "error" and "inesperado" in subs["s5"].error
        assert subs["s6"].download_status == "error" and "sin archivos" in subs["s6"].error
        assert not download.is_running(subs["s1"].assignment_id)


def test_second_run_only_downloads_new_changed_or_failed():
    with SessionLocal() as db:
        t = _teacher(db)
        _run(db, t, SUBS, FakeSource(FILES))

        files = dict(FILES, borrado=("application/pdf", pdf_bytes(1)), nuevo=("image/jpeg", jpeg_bytes(sheet_image())))
        source = FakeSource(files)
        changed = list(SUBS)
        changed[0] = _sub("s1", "u1", "TURNED_IN", ["nuevo"])  # volvió a entregar
        subs = _run(db, t, changed, source)

        assert "pdf2" not in source.calls  # s1 se baja solo con su archivo nuevo
        assert source.calls.count("nuevo") == 1
        assert "borrado" in source.calls  # reintento de error
        assert len(subs["s1"].pages) == 1
        assert subs["s3"].download_status == "lista"


def test_reclaimed_submission_deletes_images():
    with SessionLocal() as db:
        t = _teacher(db)
        subs = _run(db, t, SUBS[:1], FakeSource(FILES))
        folder = download.pages_dir(subs["s1"].id)
        assert folder.exists()
        subs = _run(db, t, [_sub("s1", "u1", "RECLAIMED_BY_STUDENT")], FakeSource(FILES))
        assert subs["s1"].download_status == "sin_entrega" and subs["s1"].pages == []
        assert not folder.exists()


def test_retention_purges_old_images_per_teacher_setting():
    with SessionLocal() as db:
        t = _teacher(db)
        t.settings.retention_days = 3
        subs = _run(db, t, SUBS[:1], FakeSource(FILES))
        sub = subs["s1"]
        folder = download.pages_dir(sub.id)

        assert purge_expired_images(db, now=utcnow() + timedelta(days=2)) == 0
        assert folder.exists()

        assert purge_expired_images(db, now=utcnow() + timedelta(days=4)) == 1
        db.expire_all()
        sub = db.get(Submission, sub.id)
        assert sub.download_status == "expirada" and sub.pages == []
        assert not folder.exists()


def test_interrupted_downloads_are_requeued():
    with SessionLocal() as db:
        t = _teacher(db)
        a = download.sync_submissions(db, t.id, reader(SUBS[:1]), "c1", "w1")
        a.submissions[0].download_status = "descargando"
        db.commit()
        assert download.reset_interrupted(db) == 1
        db.expire_all()
        assert db.get(Submission, a.submissions[0].id).download_status == "pendiente"
