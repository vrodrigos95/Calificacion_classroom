"""Etapa 2: sincroniza las entregas de una tarea y descarga cada una como páginas JPEG.

Cada entrega se procesa por separado: si una falla, queda en estado "error" con el
motivo y las demás siguen. Los logs solo llevan IDs internos, nunca nombres.
"""

import logging
import shutil
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy.orm import Session

from app.classroom.client import ClassroomReader
from app.config import get_settings
from app.db.models import (
    DL_DESCARGANDO,
    DL_ERROR,
    DL_EXPIRADA,
    DL_LISTA,
    DL_PENDIENTE,
    DL_SIN_ENTREGA,
    Assignment,
    Page,
    Submission,
    utcnow,
)
from app.db.session import SessionLocal
from app.files.base import FileFetchError, FileSource
from app.imaging.convert import UnsupportedFile, to_pages
from app.logging_conf import RedactionFilter

log = logging.getLogger(__name__)

MAX_WORKERS = 4

# Tareas con descarga en curso en este proceso (evita dos lotes simultáneos).
_running: set[int] = set()
_running_lock = threading.Lock()


def is_running(assignment_id: int) -> bool:
    with _running_lock:
        return assignment_id in _running


def pages_dir(submission_id: int) -> Path:
    return Path(get_settings().data_dir) / "pages" / str(submission_id)


def delete_page_files(submission_id: int) -> None:
    shutil.rmtree(pages_dir(submission_id), ignore_errors=True)


def sync_submissions(
    db: Session, teacher_id: int, reader: ClassroomReader, course_id: str, coursework_id: str
) -> Assignment:
    """Crea o actualiza la tarea y sus entregas a partir de Classroom."""
    cw = reader.get_coursework(course_id, coursework_id)
    assignment = (
        db.query(Assignment).filter_by(teacher_id=teacher_id, coursework_id=coursework_id).one_or_none()
    )
    if assignment is None:
        assignment = Assignment(teacher_id=teacher_id, course_id=course_id, coursework_id=coursework_id)
        db.add(assignment)
    assignment.title = cw.title

    existing = {s.classroom_submission_id: s for s in assignment.submissions}
    for live in reader.list_submissions(course_id, coursework_id):
        RedactionFilter.register_sensitive(live.student_name)
        sub = existing.get(live.id)
        if sub is None:
            sub = Submission(classroom_submission_id=live.id, attachment_ids="")
            assignment.submissions.append(sub)
        sub.student_user_id = live.user_id
        sub.student_name = live.student_name
        sub.alternate_link = live.alternate_link
        sub.classroom_state = live.state
        sub.delivered = live.delivered
        sub.late = live.late

        ids = " ".join(a.file_id for a in live.attachments)
        if not live.delivered:
            if sub.id:
                delete_page_files(sub.id)
            sub.pages.clear()
            sub.download_status, sub.error = DL_SIN_ENTREGA, None
        elif not live.attachments:
            sub.pages.clear()
            sub.download_status = DL_ERROR
            sub.error = "Entregó sin archivos (solo enlaces o formularios)"
        elif ids != sub.attachment_ids or sub.download_status in (DL_SIN_ENTREGA, DL_EXPIRADA):
            # Nueva entrega o volvió a entregar con otros archivos.
            sub.download_status, sub.error = DL_PENDIENTE, None
        sub.attachment_ids = ids if live.delivered else ""
    db.commit()
    return assignment


def queue_retry_errors(db: Session, assignment: Assignment) -> None:
    """Vuelve a poner en cola las entregas con error que sí tienen archivos."""
    for sub in assignment.submissions:
        if sub.download_status == DL_ERROR and sub.attachment_ids:
            sub.download_status, sub.error = DL_PENDIENTE, None
    db.commit()


def process_submission(submission_id: int, source: FileSource) -> None:
    """Descarga y convierte una entrega. Nunca lanza: registra el error en la entrega."""
    with SessionLocal() as db:
        sub = db.get(Submission, submission_id)
        if sub is None or sub.download_status != DL_PENDIENTE:
            return
        sub.download_status = DL_DESCARGANDO
        db.commit()

        out_dir = pages_dir(sub.id)
        try:
            delete_page_files(sub.id)
            out_dir.mkdir(parents=True, exist_ok=True)
            sub.pages.clear()
            index = 0
            for file_id in sub.attachment_ids.split():
                fetched = source.fetch(file_id)
                for page in to_pages(fetched.data, fetched.mime_type):
                    rel = Path("pages") / str(sub.id) / f"{index:03d}.jpg"
                    (Path(get_settings().data_dir) / rel).write_bytes(page.jpeg)
                    sub.pages.append(
                        Page(
                            index=index,
                            path=rel.as_posix(),
                            width=page.width,
                            height=page.height,
                            source_file_id=file_id,
                        )
                    )
                    index += 1
            sub.download_status, sub.error = DL_LISTA, None
            sub.downloaded_at = utcnow()
            db.commit()
            log.info("Entrega %s descargada: %s páginas", sub.id, index)
        except (FileFetchError, UnsupportedFile) as exc:
            _fail(db, sub, str(exc))
        except Exception:
            log.exception("Error inesperado al descargar la entrega %s", submission_id)
            _fail(db, sub, "Error inesperado al descargar o convertir el archivo")


def _fail(db: Session, sub: Submission, message: str) -> None:
    db.rollback()
    delete_page_files(sub.id)
    sub = db.get(Submission, sub.id)
    sub.pages.clear()
    sub.download_status, sub.error = DL_ERROR, message
    db.commit()
    log.warning("Entrega %s con error: %s", sub.id, message)


def try_claim(assignment_id: int) -> bool:
    """Marca la tarea como en descarga. False si ya había un lote en curso."""
    with _running_lock:
        if assignment_id in _running:
            return False
        _running.add(assignment_id)
        return True


def run_downloads(assignment_id: int, source_factory: Callable[[], FileSource]) -> None:
    """Descarga las entregas pendientes de la tarea (en paralelo, acotado).

    Requiere haber llamado try_claim(). Repite mientras aparezcan pendientes nuevas
    (p. ej. el docente pidió reintentar mientras corría el lote).
    """
    try:
        local = threading.local()

        def work(sub_id: int) -> None:
            # httplib2 no es thread-safe: un servicio de Drive por hilo.
            if not hasattr(local, "source"):
                local.source = source_factory()
            process_submission(sub_id, local.source)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            while True:
                with SessionLocal() as db:
                    ids = [
                        s.id
                        for s in db.query(Submission).filter_by(
                            assignment_id=assignment_id, download_status=DL_PENDIENTE
                        )
                    ]
                if not ids:
                    break
                log.info("Tarea %s: descargando %s entregas", assignment_id, len(ids))
                list(pool.map(work, ids))
    except Exception:
        log.exception("Falló el lote de descarga de la tarea %s", assignment_id)
    finally:
        with _running_lock:
            _running.discard(assignment_id)


def reset_interrupted(db: Session) -> int:
    """Al arrancar: las entregas que quedaron a medias vuelven a la cola."""
    n = (
        db.query(Submission)
        .filter_by(download_status=DL_DESCARGANDO)
        .update({Submission.download_status: DL_PENDIENTE})
    )
    db.commit()
    return n
