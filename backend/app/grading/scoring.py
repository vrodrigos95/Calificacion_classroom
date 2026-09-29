"""Calificación y comentario a partir de la salida del modelo. Todo es determinista.

Reglas:
- Cada ejercicio vale 100 / n. Error menor = factor × valor (0.5 por defecto).
- Un ejercicio solo cuenta como correcto si se leyó con claridad y con confianza
  suficiente; si no, vale 0 en la sugerencia y la entrega queda "revisar a mano".
- Ilegible, ambiguo, no evaluado o enunciado distinto: "revisar a mano".
"""

import re
from dataclasses import asdict, dataclass

from app.grading.schemas import ExerciseGrade, GradingOut, KeyExercise

EFFECTIVE_POR_REVISAR = "por_revisar"  # el modelo dijo correcto pero no lo leyó con claridad
EFFECTIVE_NO_EVALUADO = "no_evaluado"  # el modelo no devolvió ese ejercicio

_SUPERSCRIPT = str.maketrans("0123456789+-=()ni", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ")
_POWER_RE = re.compile(r"(\^|\*\*)\s*(\()?([-+]?[0-9ni]+)(\))?")


def superscripts(text: str) -> str:
    """x^2 → x², 2**3 → 2³, 10^(-3) → 10⁻³. No toca lo que no es exponente simple."""

    def repl(m: re.Match) -> str:
        return m.group(3).translate(_SUPERSCRIPT)

    return _POWER_RE.sub(repl, text)


@dataclass
class ExerciseResult:
    numero: str
    estado: str  # estado del modelo o EFFECTIVE_*
    puntos: float
    valor: float
    legibilidad: str
    confianza: float
    tipo_error: str
    descripcion_error: str
    comentario_alumno: str
    transcripcion_resultado: str
    valores_intermedios: list[str]
    paginas: list[int]
    motivo_revision: str


@dataclass
class ScoreResult:
    score: float
    needs_review: bool
    review_reasons: list[str]
    comment: str
    exercises: list[ExerciseResult]

    def detail(self) -> list[dict]:
        return [asdict(e) for e in self.exercises]


def _norm(numero: str) -> str:
    return re.sub(r"[^0-9a-z]", "", numero.lower().replace("ejercicio", ""))


def compute(key: list[KeyExercise], out: GradingOut, minor_factor: float, min_confidence: float) -> ScoreResult:
    n = len(key)
    if n == 0:
        raise ValueError("La clave no tiene ejercicios")
    valor = 100 / n
    by_num: dict[str, ExerciseGrade] = {}
    for e in out.ejercicios:
        by_num.setdefault(_norm(e.numero), e)
    not_found = {_norm(x) for x in out.ejercicios_no_encontrados}

    reasons: list[str] = []
    if not out.enunciado_coincide_con_clave:
        reasons.append("Los ejercicios de la hoja no coinciden con la clave")

    results: list[ExerciseResult] = []
    for k in key:
        g = by_num.get(_norm(k.numero))
        if g is None:
            estado = "no_contestado" if _norm(k.numero) in not_found else EFFECTIVE_NO_EVALUADO
            motivo = "" if estado == "no_contestado" else "El modelo no evaluó este ejercicio"
            if motivo:
                reasons.append(f"Ejercicio {k.numero}: {motivo.lower()}")
            results.append(
                ExerciseResult(k.numero, estado, 0.0, valor, "", 0.0, "", "", "", "", [], [], motivo)
            )
            continue

        conf = g.confianza
        if not 0 <= conf <= 1:
            raise ValueError("Confianza fuera de rango en la respuesta del modelo")
        estado, motivo = g.estado, ""
        if g.estado == "ilegible" or g.legibilidad == "ilegible":
            estado, motivo = "ilegible", "Ilegible"
        elif g.ambiguo:
            motivo = f"Ambiguo: {g.motivo_ambiguedad}".rstrip(": ")
        elif g.estado in ("correcto", "error_menor") and (g.legibilidad != "clara" or conf < min_confidence):
            motivo = "No se leyó con claridad" if g.legibilidad != "clara" else f"Confianza baja ({conf:.2f})"
        elif conf < min_confidence:
            motivo = f"Confianza baja ({conf:.2f})"

        # Nunca "correcto" si no se leyó con claridad: vale 0 en la sugerencia y se revisa.
        if estado == "correcto" and motivo:
            estado = EFFECTIVE_POR_REVISAR
        if estado == "correcto":
            puntos = valor
        elif estado == "error_menor":
            puntos = valor * minor_factor
        else:
            puntos = 0.0
        if motivo:
            reasons.append(f"Ejercicio {k.numero}: {motivo}")
        results.append(
            ExerciseResult(
                numero=k.numero,
                estado=estado,
                puntos=puntos,
                valor=valor,
                legibilidad=g.legibilidad,
                confianza=conf,
                tipo_error=g.tipo_error,
                descripcion_error=g.descripcion_error,
                comentario_alumno=superscripts(g.comentario_alumno.strip()),
                transcripcion_resultado=g.transcripcion_resultado,
                valores_intermedios=g.valores_intermedios,
                paginas=g.paginas,
                motivo_revision=motivo,
            )
        )

    score = round(sum(r.puntos for r in results), 1)
    return ScoreResult(score, bool(reasons), reasons, build_comment(results), results)


_DEFAULT_LINE = {
    "incorrecto": "revísalo, el resultado no es correcto.",
    "incompleto": "está incompleto; termínalo.",
    "no_contestado": "no lo contestaste.",
    "ilegible": "no se alcanza a leer; escríbelo más claro.",
    "error_menor": "casi está; revisa el resultado y la notación.",
}


def build_comment(results: list[ExerciseResult]) -> str:
    """Una línea por ejercicio con problema. Si todo está bien, una confirmación breve."""
    lines = []
    for r in results:
        if r.estado == "correcto":
            continue
        if r.estado in (EFFECTIVE_POR_REVISAR, EFFECTIVE_NO_EVALUADO):
            continue  # lo decide el docente; no se le dice nada al alumno todavía
        text = r.comentario_alumno or _DEFAULT_LINE.get(r.estado, "revísalo.")
        text = text[0].lower() + text[1:] if text[:1].isupper() and not text[:2].isupper() else text
        lines.append(f"Ejercicio {r.numero}: {text}")
    if not lines:
        if all(r.estado == "correcto" for r in results):
            return "¡Muy bien! Todos los ejercicios están correctos."
        return ""
    return " ".join(lines)
