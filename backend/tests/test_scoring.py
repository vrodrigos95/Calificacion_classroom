import pytest

from app.grading.schemas import GradingOut, KeyExercise
from app.grading.scoring import compute, superscripts

KEY = [
    KeyExercise(numero="1", respuesta_final="33%"),
    KeyExercise(numero="2", respuesta_final="15.38%"),
    KeyExercise(numero="3", respuesta_final="40%"),
    KeyExercise(numero="4", respuesta_final="P(A ∪ B) = 70%", criterios_notacion=["usar ∪ para 'o'", "en porcentaje"]),
]


def ex(numero, estado="correcto", legibilidad="clara", confianza=0.95, ambiguo=False, comentario="", tipo="ninguno"):
    return {
        "numero": numero,
        "paginas": [1],
        "legibilidad": legibilidad,
        "confianza": confianza,
        "ambiguo": ambiguo,
        "motivo_ambiguedad": "se ve 4 o 9" if ambiguo else "",
        "transcripcion_resultado": "",
        "valores_intermedios": [],
        "estado": estado,
        "tipo_error": tipo,
        "descripcion_error": "",
        "comentario_alumno": comentario,
    }


def out(*exercises, coincide=True, no_encontrados=()):
    return GradingOut.model_validate(
        {
            "ejercicios": list(exercises),
            "ejercicios_no_encontrados": list(no_encontrados),
            "enunciado_coincide_con_clave": coincide,
            "observaciones": "",
        }
    )


def test_caso_de_prueba_del_docente_da_75():
    """Tarea de 4 ejercicios: 1 y 2 correctos, 3 error menor (4% vs 40%), 4 error menor de notación."""
    r = compute(
        KEY,
        out(
            ex("1"),
            ex("2"),
            ex("3", "error_menor", comentario="tu procedimiento está bien, pero 0.4 equivale a 40%, no a 4%.", tipo="conversion"),
            ex("4", "error_menor", comentario="el resultado es correcto; 'o' es unión (∪), no intersección (∩), y agrega el porcentaje como en los demás.", tipo="notacion"),
        ),
        minor_factor=0.5,
        min_confidence=0.8,
    )
    assert r.score == 75.0
    assert not r.needs_review
    assert r.comment == (
        "Ejercicio 3: tu procedimiento está bien, pero 0.4 equivale a 40%, no a 4%. "
        "Ejercicio 4: el resultado es correcto; 'o' es unión (∪), no intersección (∩), "
        "y agrega el porcentaje como en los demás."
    )


def test_all_correct_gives_short_confirmation():
    r = compute(KEY, out(*(ex(str(i)) for i in range(1, 5))), 0.5, 0.8)
    assert r.score == 100 and r.comment == "¡Muy bien! Todos los ejercicios están correctos."


def test_minor_error_factor_is_configurable():
    r = compute(KEY, out(ex("1"), ex("2"), ex("3", "error_menor"), ex("4")), minor_factor=0.25, min_confidence=0.8)
    assert r.score == pytest.approx(81.2, abs=0.1)  # 75 + 6.25


@pytest.mark.parametrize(
    "bad",
    [
        ex("2", legibilidad="parcial"),  # "correcto" pero no se leyó con claridad
        ex("2", confianza=0.6),  # "correcto" con confianza baja
        ex("2", "ilegible", legibilidad="ilegible"),
        ex("2", ambiguo=True),
    ],
)
def test_never_correct_without_clear_reading(bad):
    r = compute(KEY, out(ex("1"), bad, ex("3"), ex("4")), 0.5, 0.8)
    assert r.needs_review
    e2 = r.exercises[1]
    assert e2.estado != "correcto" or bad["ambiguo"]
    if e2.estado != "correcto":
        assert e2.puntos == 0
    assert "Ejercicio 2" in r.review_reasons[0]


def test_missing_and_not_found_exercises():
    r = compute(KEY, out(ex("1"), ex("2"), ex("3"), no_encontrados=["4"]), 0.5, 0.8)
    assert r.exercises[3].estado == "no_contestado" and not r.needs_review
    assert "Ejercicio 4: no lo contestaste." in r.comment

    r = compute(KEY, out(ex("1"), ex("2"), ex("3")), 0.5, 0.8)  # el modelo omitió el 4
    assert r.exercises[3].estado == "no_evaluado" and r.needs_review


def test_statement_mismatch_forces_review():
    r = compute(KEY, out(*(ex(str(i)) for i in range(1, 5)), coincide=False), 0.5, 0.8)
    assert r.needs_review and r.score == 100


def test_exercise_numbers_are_matched_loosely():
    r = compute(KEY, out(ex("Ejercicio 1"), ex("2."), ex("(3)"), ex("4")), 0.5, 0.8)
    assert r.score == 100


def test_out_of_range_confidence_is_rejected():
    with pytest.raises(ValueError):
        compute(KEY, out(ex("1", confianza=1.5), ex("2"), ex("3"), ex("4")), 0.5, 0.8)


@pytest.mark.parametrize(
    "raw,expected",
    [("x^2 + 2^3", "x² + 2³"), ("2**10", "2¹⁰"), ("10^(-3)", "10⁻³"), ("x^n", "xⁿ"), ("40% y 0.4", "40% y 0.4")],
)
def test_superscripts(raw, expected):
    assert superscripts(raw) == expected


def test_comments_get_superscripts():
    r = compute(KEY, out(ex("1", "incorrecto", comentario="revisa x^2, no es 2x"), ex("2"), ex("3"), ex("4")), 0.5, 0.8)
    assert "x²" in r.comment and "^" not in r.comment
