"""Borra las imágenes descargadas tras N días (configurable por docente)."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import DL_EXPIRADA, DL_LISTA, Assignment, Submission, Teacher, utcnow
from app.pipeline.download import delete_page_files

log = logging.getLogger(__name__)


def _aware(dt: datetime) -> datetime:
    # SQLite devuelve fechas sin zona; se guardaron en UTC.
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def purge_expired_images(db: Session, now: datetime | None = None) -> int:
    now = now or utcnow()
    default_days = get_settings().retention_days
    purged = 0
    for teacher in db.query(Teacher):
        days = (teacher.settings.retention_days if teacher.settings else None) or default_days
        cutoff = now - timedelta(days=days)
        subs = (
            db.query(Submission)
            .join(Assignment)
            .filter(Assignment.teacher_id == teacher.id, Submission.download_status == DL_LISTA)
        )
        for sub in subs:
            if sub.downloaded_at and _aware(sub.downloaded_at) < cutoff:
                delete_page_files(sub.id)
                sub.pages.clear()
                sub.download_status = DL_EXPIRADA
                purged += 1
    db.commit()
    if purged:
        log.info("Retención: se borraron las imágenes de %s entregas", purged)
    return purged
