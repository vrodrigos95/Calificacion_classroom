"""Modelos de la BD.

Etapa 1: docente, token OAuth y configuración por docente.
Etapa 2: tareas, entregas y páginas descargadas.
Etapa 3: marcas de validación del docente y su detección en cada entrega.
Etapa 4: clave de respuestas por tarea y calificación de cada entrega.

De los alumnos solo se guarda lo necesario para el panel: su userId de Classroom,
su nombre y el enlace a la entrega. Nunca su correo.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Teacher(Base):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    google_sub: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    token: Mapped["OAuthToken | None"] = relationship(
        back_populates="teacher", uselist=False, cascade="all, delete-orphan"
    )
    settings: Mapped["TeacherSettings | None"] = relationship(
        back_populates="teacher", uselist=False, cascade="all, delete-orphan"
    )


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"), unique=True
    )
    refresh_token_enc: Mapped[bytes] = mapped_column(LargeBinary)
    scopes: Mapped[str] = mapped_column(String(2000))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    teacher: Mapped[Teacher] = relationship(back_populates="token")


class TeacherSettings(Base):
    """Criterios configurables por docente. None = usar el default global."""

    __tablename__ = "teacher_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"), unique=True
    )
    minor_error_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mark_accept_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    mark_doubtful_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    exercise_min_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    teacher: Mapped[Teacher] = relationship(back_populates="settings")


MODE_EJERCICIOS = "ejercicios"
MODE_SOLO_FIRMA = "solo_firma"
DEFAULT_UNSIGNED_SCORE = 90.0
DEFAULT_UNSIGNED_COMMENT = "La actividad tiene que estar firmada"


class Assignment(Base):
    """Una tarea de Classroom que el docente procesa en la app."""

    __tablename__ = "assignments"
    __table_args__ = (UniqueConstraint("teacher_id", "coursework_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"))
    course_id: Mapped[str] = mapped_column(String(64))
    coursework_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(300), default="")
    # Configuración por tarea (etapas 3 y 4). None = usar la del docente.
    mark_module_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    minor_error_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Modo de calificación: "ejercicios" (clave + Claude) o "solo_firma" (con firma = 100;
    # sin firma = unsigned_score con unsigned_comment). El modo solo firma no usa Claude.
    grading_mode: Mapped[str] = mapped_column(String(20), default=MODE_EJERCICIOS, server_default=MODE_EJERCICIOS)
    unsigned_score: Mapped[float] = mapped_column(Float, default=DEFAULT_UNSIGNED_SCORE, server_default="90")
    unsigned_comment: Mapped[str] = mapped_column(
        Text, default=DEFAULT_UNSIGNED_COMMENT, server_default=DEFAULT_UNSIGNED_COMMENT
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    submissions: Mapped[list["Submission"]] = relationship(
        back_populates="assignment", cascade="all, delete-orphan"
    )
    answer_key: Mapped["AnswerKey | None"] = relationship(
        back_populates="assignment", uselist=False, cascade="all, delete-orphan"
    )


# Estados de descarga de una entrega
DL_SIN_ENTREGA = "sin_entrega"
DL_PENDIENTE = "pendiente"
DL_DESCARGANDO = "descargando"
DL_LISTA = "lista"
DL_ERROR = "error"
DL_EXPIRADA = "expirada"  # las imágenes se borraron por retención


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("assignment_id", "classroom_submission_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"))
    classroom_submission_id: Mapped[str] = mapped_column(String(64))
    student_user_id: Mapped[str] = mapped_column(String(64))
    student_name: Mapped[str] = mapped_column(String(200))
    alternate_link: Mapped[str] = mapped_column(String(500), default="")
    classroom_state: Mapped[str] = mapped_column(String(32), default="")
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    late: Mapped[bool] = mapped_column(Boolean, default=False)
    # IDs de Drive de los archivos entregados, separados por espacio. Si cambian (el alumno
    # volvió a entregar), la entrega se descarga de nuevo.
    attachment_ids: Mapped[str] = mapped_column(Text, default="")
    download_status: Mapped[str] = mapped_column(String(20), default=DL_PENDIENTE)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Módulo de marca (etapa 3). mark_status: ver MK_* abajo; None = aún no se revisa.
    mark_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    mark_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Decisión del docente sobre la marca: True = confirmó, False = rechazó, None = sin decidir.
    mark_confirmed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Panel (etapa 5): lo que el docente ajusta y si ya lo capturó en Classroom.
    score_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    comment_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    captured: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    assignment: Mapped[Assignment] = relationship(back_populates="submissions")
    pages: Mapped[list["Page"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan", order_by="Page.index"
    )
    detections: Mapped[list["MarkDetection"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan", order_by="MarkDetection.id"
    )
    grade: Mapped["Grade | None"] = relationship(
        back_populates="submission", uselist=False, cascade="all, delete-orphan"
    )


class Page(Base):
    """Una página (imagen) de una entrega. El archivo vive en DATA_DIR/pages/."""

    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"))
    index: Mapped[int] = mapped_column(Integer)  # 0 = primera página de la entrega
    path: Mapped[str] = mapped_column(String(500))  # relativo a DATA_DIR
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    source_file_id: Mapped[str] = mapped_column(String(128))

    submission: Mapped[Submission] = relationship(back_populates="pages")


# Significado y zona de búsqueda de una marca
MEANING_CORRECTA = "correcta"  # la entrega vale 100 y no se revisa el contenido
MEANING_INFORMATIVA = "informativa"  # se muestra, pero la tarea se revisa normal
ZONE_PRIMERA = "primera"
ZONE_CUALQUIERA = "cualquiera"


class ValidationMark(Base):
    """Firma o sello del docente, con su significado y dónde buscarlo."""

    __tablename__ = "validation_marks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    meaning: Mapped[str] = mapped_column(String(20), default=MEANING_CORRECTA)
    zone: Mapped[str] = mapped_column(String(20), default=ZONE_PRIMERA)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    profile_json: Mapped[str] = mapped_column(Text, default="{}")  # ColorProfile
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    references: Mapped[list["MarkReference"]] = relationship(
        back_populates="mark", cascade="all, delete-orphan", order_by="MarkReference.id"
    )


class MarkReference(Base):
    """Imagen de referencia de una marca. Vive en DATA_DIR/marks/ (no aplica retención)."""

    __tablename__ = "mark_references"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mark_id: Mapped[int] = mapped_column(ForeignKey("validation_marks.id", ondelete="CASCADE"))
    path: Mapped[str] = mapped_column(String(500))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)

    mark: Mapped[ValidationMark] = relationship(back_populates="references")


# Resultado del módulo de marca en una entrega
MK_CON_MARCA = "con_marca"
MK_DUDOSA = "dudosa"
MK_SIN_MARCA = "sin_marca"
MK_ERROR = "error"
MK_DESACTIVADO = "desactivado"
MK_SIN_CONFIG = "sin_config"  # el docente no tiene marcas activas
MK_NO_REVISABLE = "no_revisable"  # la entrega no tiene imágenes

# Veredicto por candidato
V_MARCA = "marca"
V_DUDOSA = "dudosa"
V_NO_MARCA = "no_marca"


class MarkDetection(Base):
    """Un candidato encontrado en una página, con su recorte y el veredicto."""

    __tablename__ = "mark_detections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"))
    mark_id: Mapped[int | None] = mapped_column(
        ForeignKey("validation_marks.id", ondelete="SET NULL"), nullable=True
    )
    page_index: Mapped[int] = mapped_column(Integer)
    x0: Mapped[int] = mapped_column(Integer)
    y0: Mapped[int] = mapped_column(Integer)
    x1: Mapped[int] = mapped_column(Integer)
    y1: Mapped[int] = mapped_column(Integer)
    crop_path: Mapped[str] = mapped_column(String(500))  # relativo a DATA_DIR (con las páginas)
    confidence: Mapped[float] = mapped_column(Float)
    verdict: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text, default="")
    verifier: Mapped[str] = mapped_column(String(20))

    submission: Mapped[Submission] = relationship(back_populates="detections")
    mark: Mapped[ValidationMark | None] = relationship()


# Origen de la clave de respuestas
KEY_DOCENTE = "docente"  # el docente la subió (texto, foto o PDF) o la capturó
KEY_RESUELTA = "resuelta_por_modelo"  # el modelo resolvió los enunciados

# Estado del trabajo en segundo plano sobre la clave
KJ_LISTA = "lista"
KJ_GENERANDO = "generando"
KJ_ERROR = "error"


class AnswerKey(Base):
    """Clave de respuestas de una tarea. Nunca se califica con una clave sin validar."""

    __tablename__ = "answer_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), unique=True
    )
    source: Mapped[str] = mapped_column(String(30), default=KEY_DOCENTE)
    # De dónde salió el enunciado (descripción/adjuntos de Classroom, hojas de alumnos…)
    statement_source: Mapped[str | None] = mapped_column(String(40), nullable=True)
    exercises_json: Mapped[str] = mapped_column(Text, default="[]")
    warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)  # sube con cada cambio
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    job_status: Mapped[str] = mapped_column(String(20), default=KJ_LISTA)
    job_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    assignment: Mapped[Assignment] = relationship(back_populates="answer_key")


# Estado de la calificación de una entrega
G_CALIFICANDO = "calificando"
G_REVISADA = "revisada"  # lista: el docente solo revisa y copia
G_REVISAR = "revisar_a_mano"  # hay algo ilegible, ambiguo o dudoso: sugerida pero no lista
G_CON_MARCA = "con_marca"  # 100 por marca "tarea correcta", sin revisar contenido
G_ERROR = "error"


class Grade(Base):
    """Calificación sugerida de una entrega."""

    __tablename__ = "grades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[str] = mapped_column(String(20), default=G_CALIFICANDO)
    key_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)  # sobre 100
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)  # sugerido
    review_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)  # por qué revisar a mano
    detail_json: Mapped[str] = mapped_column(Text, default="[]")  # resultado por ejercicio
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(60), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    submission: Mapped[Submission] = relationship(back_populates="grade")
