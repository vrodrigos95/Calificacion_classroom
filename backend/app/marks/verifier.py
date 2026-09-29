"""Verificación de candidatos a marca: local (sin costo) o con Claude.

Reglas de seguridad (en marks/service.py):
- Solo una confianza >= umbral de aceptación da "con_marca".
- La verificación local nunca acepta sola: como mucho deja "dudosa" para que el
  docente confirme con el recorte a la vista.
"""

import io
import logging
from dataclasses import dataclass
from typing import Protocol

import anthropic
from PIL import Image
from pydantic import BaseModel, Field

from app.config import get_settings
from app.vision.claude_client import ClaudeClient, VisionError, image_block, text_block

log = logging.getLogger(__name__)


@dataclass
class ReferenceSet:
    mark_id: int
    name: str
    images_png: list[bytes]


@dataclass
class CandidateCrop:
    candidate_id: str  # p. ej. "p1_c1"
    png: bytes


@dataclass
class CandidateVerdict:
    candidate_id: str
    is_mark: bool
    mark_id: int | None
    confidence: float  # 0..1
    reason: str
    verifier: str  # "local" | "claude"


# La verificación no se pudo completar; la entrega va a revisión manual.
VerificationError = VisionError


class Verifier(Protocol):
    name: str

    def verify(self, refs: list[ReferenceSet], crops: list[CandidateCrop]) -> list[CandidateVerdict]: ...


class LocalVerifier:
    """Sin modelo: un candidato con la tinta y el tamaño de la marca es 'posible marca'.

    La confianza que devuelve está topada por debajo del umbral de aceptación, así que
    nunca produce "con_marca" por sí sola.
    """

    name = "local"
    CAPPED_CONFIDENCE = 0.7

    def verify(self, refs, crops):
        mark_id = refs[0].mark_id if len(refs) == 1 else None
        return [
            CandidateVerdict(
                candidate_id=c.candidate_id,
                is_mark=True,
                mark_id=mark_id,
                confidence=self.CAPPED_CONFIDENCE,
                reason="Tinta del color de tu marca (verificación local: confírmala)",
                verifier=self.name,
            )
            for c in crops
        ]


# ---- Claude ---------------------------------------------------------------------------

class _CandidateOut(BaseModel):
    candidato_id: str
    es_marca: bool
    marca_referencia_id: int | None = Field(description="id de la marca de referencia que coincide, o null")
    confianza: float = Field(description="0 a 1: qué tan seguro estás de que es esa marca")
    motivo: str = Field(description="Una frase en español: por qué coincide o no")


class MarkVerificationOut(BaseModel):
    candidatos: list[_CandidateOut]


SYSTEM_PROMPT = """Eres un verificador de firmas y sellos de docentes en hojas de tarea escritas a mano.
Recibes imágenes de referencia de la marca del docente y recortes candidatos tomados de la
hoja de un alumno. Para cada candidato decide si es la marca del docente.

Criterios:
- Compara la forma del trazo, su estructura y proporciones, el tipo de trazo y el color.
- La marca puede estar incompleta (cortada por el borde de la foto), inclinada, tenue o
  encimada sobre texto o cuadrícula; eso no la invalida si la estructura coincide.
- Texto, números, subrayados, palomitas, dibujos o decoraciones del alumno NO son la marca,
  aunque sean del mismo color.
- Si no puedes verlo con claridad, baja la confianza. Nunca inventes: una confianza alta
  solo cuando la coincidencia es evidente.
- confianza: 0.9 a 1 = coincidencia clara; 0.6 a 0.9 = parecida pero dudosa; menos de 0.6 = no es.
Devuelve un elemento por cada candidato recibido, con su candidato_id exacto."""


class ClaudeVerifier:
    name = "claude"

    def __init__(self, client: anthropic.Anthropic | None = None, model: str | None = None):
        self.claude = ClaudeClient(client, model)

    def verify(self, refs, crops):
        content: list[dict] = []
        for ref in refs:
            content.append(text_block(f"Marca de referencia id={ref.mark_id} («{ref.name}»):"))
            content.extend(image_block(p, "image/png") for p in ref.images_png)
        content.append(text_block("Candidatos encontrados en la hoja del alumno:"))
        for c in crops:
            content.append(text_block(f"candidato_id={c.candidate_id}"))
            content.append(image_block(c.png, "image/png"))
        content.append(text_block("Evalúa cada candidato."))
        parsed, _ = self.claude.structured(
            SYSTEM_PROMPT, content, MarkVerificationOut, purpose=f"verificación de marca ({len(crops)} candidatos)"
        )

        valid_ids = {c.candidate_id for c in crops}
        valid_marks = {r.mark_id for r in refs}
        out = []
        for item in parsed.candidatos:
            if item.candidato_id not in valid_ids:
                continue
            conf = item.confianza
            if not 0 <= conf <= 1:
                raise VerificationError("Claude devolvió una confianza fuera de rango")
            mark_id = item.marca_referencia_id if item.marca_referencia_id in valid_marks else None
            if len(valid_marks) == 1 and item.es_marca and mark_id is None:
                mark_id = next(iter(valid_marks))
            out.append(
                CandidateVerdict(item.candidato_id, item.es_marca, mark_id, conf, item.motivo, self.name)
            )
        missing = valid_ids - {v.candidate_id for v in out}
        for cid in missing:  # si omitió alguno, se trata como no evaluado (dudoso)
            out.append(CandidateVerdict(cid, True, None, 0.6, "Claude no evaluó este candidato", self.name))
        return out


def default_verifier() -> Verifier:
    return ClaudeVerifier() if get_settings().anthropic_api_key else LocalVerifier()


def to_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
