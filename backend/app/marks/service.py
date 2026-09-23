"""Módulo de marca de validación: configuración de marcas y detección en entregas."""

import io
import json
import logging
import shutil
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import (
    DL_LISTA,
    MEANING_CORRECTA,
    MK_CON_MARCA,
    MK_DESACTIVADO,
    MK_DUDOSA,
    MK_ERROR,
    MK_NO_REVISABLE,
    MK_SIN_CONFIG,
    MK_SIN_MARCA,
    V_DUDOSA,
    V_MARCA,
    V_NO_MARCA,
    ZONE_CUALQUIERA,
    MarkDetection,
    MarkReference,
    Submission,
    Teacher,
    ValidationMark,
)
from app.db.session import SessionLocal
from app.marks.color import ColorProfile, find_candidates, profile_from_references
from app.marks.verifier import (
    CandidateCrop,
    CandidateVerdict,
    ReferenceSet,
    VerificationError,
    Verifier,
    to_png,
)

log = logging.getLogger(__name__)

MAX_REFERENCES = 5
MAX_REFERENCE_BYTES = 10 * 1024 * 1024
FULL_PAGE_SIDE = 1400  # página completa (marcas sin color) que se envía al modelo
MAX_WORKERS = 3


class MarkConfigError(ValueError):
    pass


# ---- Configuración de marcas ------------------------------------------------------------

def _data() -> Path:
    return Path(get_settings().data_dir)


def _load_reference(data: bytes) -> Image.Image:
    if len(data) > MAX_REFERENCE_BYTES:
        raise MarkConfigError("Cada imagen de referencia debe pesar menos de 10 MB")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:
        raise MarkConfigError("Una de las imágenes de referencia no se pudo abrir") from exc
    img = ImageOps.exif_transpose(img).convert("RGBA")
    img.thumbnail((800, 800))
    return img


def set_references(db: Session, mark: ValidationMark, files: list[bytes]) -> None:
    """Reemplaza las imágenes de referencia y recalcula el perfil de color."""
    if not 1 <= len(files) <= MAX_REFERENCES:
        raise MarkConfigError(f"Sube de 1 a {MAX_REFERENCES} imágenes de referencia")
    images = [_load_reference(f) for f in files]
    profile = profile_from_references([np.array(i) for i in images])

    folder = _data() / "marks" / str(mark.id)
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)
    mark.references.clear()
    for n, img in enumerate(images):
        rel = Path("marks") / str(mark.id) / f"{n}.png"
        img.save(_data() / rel, "PNG")
        mark.references.append(MarkReference(path=rel.as_posix(), width=img.width, height=img.height))
    mark.profile_json = json.dumps(profile.to_dict())


def create_mark(
    db: Session, teacher: Teacher, name: str, meaning: str, zone: str, files: list[bytes]
) -> ValidationMark:
    mark = ValidationMark(teacher_id=teacher.id, name=name.strip() or "Mi marca", meaning=meaning, zone=zone)
    db.add(mark)
    db.flush()  # obtiene el id para la carpeta
    try:
        set_references(db, mark, files)
    except MarkConfigError:
        db.rollback()
        raise
    db.commit()
    return mark


def delete_mark(db: Session, mark: ValidationMark) -> None:
    shutil.rmtree(_data() / "marks" / str(mark.id), ignore_errors=True)
    db.delete(mark)
    db.commit()


def profile_of(mark: ValidationMark) -> ColorProfile:
    return ColorProfile.from_dict(json.loads(mark.profile_json))


# ---- Detección en una entrega ------------------------------------------------------------

@dataclass
class Thresholds:
    accept: float
    doubtful: float


def thresholds_for(teacher: Teacher) -> Thresholds:
    s = get_settings()
    ts = teacher.settings
    return Thresholds(
        accept=(ts.mark_accept_threshold if ts and ts.mark_accept_threshold is not None else s.mark_accept_threshold),
        doubtful=(
            ts.mark_doubtful_threshold if ts and ts.mark_doubtful_threshold is not None else s.mark_doubtful_threshold
        ),
    )


def verdict_for(v: CandidateVerdict, th: Thresholds) -> str:
    """Nunca 'marca' por debajo del umbral de aceptación; la verificación local nunca acepta."""
    if v.verifier == "local":
        return V_DUDOSA if v.is_mark else V_NO_MARCA
    if not v.is_mark or v.confidence < th.doubtful:
        return V_NO_MARCA
    if v.confidence >= th.accept:
        return V_MARCA
    return V_DUDOSA


def clear_mark_results(sub: Submission) -> None:
    """Borra el resultado del módulo (p. ej. si el alumno volvió a entregar)."""
    sub.detections.clear()
    sub.mark_status = sub.mark_detail = sub.mark_confirmed = None
    shutil.rmtree(_data() / "pages" / str(sub.id) / "crops", ignore_errors=True)


def _page_image(rel_path: str) -> Image.Image:
    return Image.open(_data() / rel_path).convert("RGB")


def detect_in_submission(
    db: Session, sub: Submission, marks: list[ValidationMark], verifier: Verifier, th: Thresholds
) -> None:
    """Aplica el módulo de marca a una entrega ya descargada y guarda el resultado."""
    clear_mark_results(sub)
    if not sub.pages:
        sub.mark_status, sub.mark_detail = MK_NO_REVISABLE, "La entrega no tiene imágenes"
        return

    crops_dir = _data() / "pages" / str(sub.id) / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    pages = {p.index: p for p in sub.pages}
    loaded: dict[int, Image.Image] = {}

    # 1) Prefiltro: candidatos por marca en su zona de búsqueda.
    pending: list[tuple[CandidateCrop, ValidationMark, int, tuple[int, int, int, int], Image.Image]] = []
    for mark in marks:
        profile = profile_of(mark)
        indexes = sorted(pages) if mark.zone == ZONE_CUALQUIERA else [min(pages)]
        for idx in indexes:
            img = loaded.setdefault(idx, _page_image(pages[idx].path))
            if profile.colored:
                boxes = [c.padded(img.width, img.height) for c in find_candidates(np.array(img), profile)]
            else:
                boxes = [(0, 0, img.width, img.height)]  # tinta sin color: el modelo revisa la página
            for n, box in enumerate(boxes):
                crop = img.crop(box)
                if not profile.colored:
                    crop.thumbnail((FULL_PAGE_SIDE, FULL_PAGE_SIDE))
                cid = f"m{mark.id}_p{idx + 1}_c{n + 1}"
                pending.append((CandidateCrop(cid, to_png(crop)), mark, idx, box, crop))

    if not pending:
        sub.mark_status, sub.mark_detail = MK_SIN_MARCA, "No se encontró tinta del color de tu marca"
        return

    # 2) Verificación (una sola llamada por entrega con todas las referencias).
    refs = [
        ReferenceSet(m.id, m.name, [(_data() / r.path).read_bytes() for r in m.references]) for m in marks
    ]
    error = None
    try:
        verdicts = {v.candidate_id: v for v in verifier.verify(refs, [p[0] for p in pending])}
    except VerificationError as exc:
        error = str(exc)
        verdicts = {}

    # 3) Guarda detecciones y decide el estado.
    correct_verdicts = []
    for crop_info, mark, idx, box, crop in pending:
        v = verdicts.get(crop_info.candidate_id) or CandidateVerdict(
            crop_info.candidate_id, True, mark.id, th.doubtful, error or "Sin verificar", "ninguno"
        )
        verdict = V_DUDOSA if error else verdict_for(v, th)
        target = next((m for m in marks if m.id == v.mark_id), mark)
        det = MarkDetection(
            mark_id=target.id,
            page_index=idx,
            x0=box[0], y0=box[1], x1=box[2], y1=box[3],
            crop_path="",
            confidence=v.confidence,
            verdict=verdict,
            reason=v.reason,
            verifier=v.verifier,
        )
        sub.detections.append(det)
        db.flush()
        rel = Path("pages") / str(sub.id) / "crops" / f"{det.id}.jpg"
        crop.save(_data() / rel, "JPEG", quality=90)
        det.crop_path = rel.as_posix()
        if target.meaning == MEANING_CORRECTA:
            correct_verdicts.append(verdict)

    if error:
        sub.mark_status, sub.mark_detail = MK_ERROR, error
    elif V_MARCA in correct_verdicts:
        sub.mark_status, sub.mark_detail = MK_CON_MARCA, None
    elif V_DUDOSA in correct_verdicts:
        sub.mark_status = MK_DUDOSA
        sub.mark_detail = (
            "Posible marca: confírmala con el recorte"
            if verifier.name == "local"
            else "Coincidencia dudosa: revísala con el recorte"
        )
    else:
        sub.mark_status, sub.mark_detail = MK_SIN_MARCA, None


# ---- Lote ------------------------------------------------------------------------------

_running: set[int] = set()
_running_lock = threading.Lock()


def is_running(assignment_id: int) -> bool:
    with _running_lock:
        return assignment_id in _running


def try_claim(assignment_id: int) -> bool:
    with _running_lock:
        if assignment_id in _running:
            return False
        _running.add(assignment_id)
        return True


def active_marks(db: Session, teacher_id: int) -> list[ValidationMark]:
    return (
        db.query(ValidationMark)
        .filter_by(teacher_id=teacher_id, active=True)
        .order_by(ValidationMark.id)
        .all()
    )


def _process_one(submission_id: int, verifier: Verifier) -> None:
    with SessionLocal() as db:
        sub = db.get(Submission, submission_id)
        if sub is None:
            return
        teacher = db.get(Teacher, sub.assignment.teacher_id)
        try:
            if not sub.assignment.mark_module_enabled:
                clear_mark_results(sub)
                sub.mark_status = MK_DESACTIVADO
            else:
                marks = active_marks(db, teacher.id)
                if not marks:
                    clear_mark_results(sub)
                    sub.mark_status = MK_SIN_CONFIG
                else:
                    detect_in_submission(db, sub, marks, verifier, thresholds_for(teacher))
            db.commit()
            log.info("Entrega %s: marca=%s", sub.id, sub.mark_status)
        except Exception:
            log.exception("Error inesperado en el módulo de marca, entrega %s", submission_id)
            db.rollback()
            sub = db.get(Submission, submission_id)
            clear_mark_results(sub)
            sub.mark_status, sub.mark_detail = MK_ERROR, "Error inesperado al buscar la marca"
            db.commit()


def run_mark_detection(assignment_id: int, verifier_factory: Callable[[], Verifier]) -> None:
    """Revisa la marca en todas las entregas descargadas que el docente no ha decidido.

    Requiere haber llamado try_claim().
    """
    try:
        with SessionLocal() as db:
            ids = [
                s.id
                for s in db.query(Submission).filter_by(assignment_id=assignment_id, download_status=DL_LISTA)
                if s.mark_confirmed is None
            ]
        verifier = verifier_factory()
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            list(pool.map(lambda i: _process_one(i, verifier), ids))
    except Exception:
        log.exception("Falló el lote de marcas de la tarea %s", assignment_id)
    finally:
        with _running_lock:
            _running.discard(assignment_id)


def effective_status(sub: Submission) -> str | None:
    """Estado de marca considerando la decisión del docente."""
    if sub.mark_confirmed is True:
        return MK_CON_MARCA
    if sub.mark_confirmed is False:
        return MK_SIN_MARCA
    return sub.mark_status

