"""Modelos de la BD. Etapa 1: docente, token OAuth y configuración por docente.

Las tablas de tareas, entregas, marcas y resultados se agregan en etapas siguientes.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, LargeBinary, String
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
