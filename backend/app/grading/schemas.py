"""Esquemas JSON de entrada y salida del modelo (validados con Pydantic).

Nota: la salida estructurada de Claude no admite `minimum`/`maximum`; los rangos
(p. ej. confianza entre 0 y 1) se validan en el código después de recibir la respuesta.
"""

from typing import Literal

from pydantic import BaseModel, Field

# ---- Clave de respuestas ----------------------------------------------------------------


class KeyExercise(BaseModel):
    """Un ejercicio de la clave, tal como se guarda y se edita."""

    numero: str = Field(description='Número o etiqueta del ejercicio, p. ej. "3" o "3a"')
    enunciado: str = Field(default="", description="Texto del enunciado (vacío si no se conoce)")
    respuesta_final: str = Field(description="Resultado correcto, con la notación esperada")
    procedimiento_clave: str = Field(default="", description="Pasos o planteamiento esperados, breve")
    criterios_notacion: list[str] = Field(
        default_factory=list, description='Exigencias de formato, p. ej. "expresar en porcentaje"'
    )


class _KeyExerciseOut(KeyExercise):
    confianza: float = Field(description="0 a 1: qué tan seguro estás de esta respuesta")


class KeyModelOut(BaseModel):
    ejercicios: list[_KeyExerciseOut]
    observaciones: str = Field(description="Dudas o avisos para el docente; vacío si no hay")


class _StatementExercise(BaseModel):
    numero: str
    enunciado: str


class StatementOut(BaseModel):
    enunciado_encontrado: bool = Field(
        description="true solo si en el material se ven los enunciados de los ejercicios"
    )
    ejercicios: list[_StatementExercise]
    observaciones: str


# ---- Calificación de una entrega ----------------------------------------------------------

Legibilidad = Literal["clara", "parcial", "ilegible"]
Estado = Literal["correcto", "error_menor", "incorrecto", "incompleto", "no_contestado", "ilegible"]
TipoError = Literal["ninguno", "resultado", "notacion", "conversion", "procedimiento", "otro"]


class ExerciseGrade(BaseModel):
    numero: str
    paginas: list[int] = Field(description="Páginas (desde 1) donde aparece el ejercicio")
    legibilidad: Legibilidad
    confianza: float = Field(description="0 a 1: qué tan seguro estás de tu lectura y evaluación")
    ambiguo: bool = Field(description="true si la respuesta admite más de una lectura")
    motivo_ambiguedad: str
    transcripcion_resultado: str = Field(description="El resultado final tal como lo escribió el alumno")
    valores_intermedios: list[str] = Field(description="Valores intermedios que escribió el alumno")
    estado: Estado
    tipo_error: TipoError
    descripcion_error: str = Field(description="Error concreto, para el docente; vacío si no hay")
    comentario_alumno: str = Field(
        description="Para el alumno, de tú: el error concreto y qué corregir, sin resolverle el ejercicio. "
        "Vacío si está correcto."
    )


class GradingOut(BaseModel):
    ejercicios: list[ExerciseGrade]
    ejercicios_no_encontrados: list[str] = Field(description="Números de la clave que no aparecen en la hoja")
    enunciado_coincide_con_clave: bool
    observaciones: str
