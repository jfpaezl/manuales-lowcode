"""Tests de la detección y relleno de huecos [COMPLETAR] (texto puro, sin IA)."""
from src.application import pending


def test_find_pending_detecta_huecos_con_su_seccion():
    md = (
        "## Datos generales\n"
        "Responsable | [COMPLETAR]\n"
        "## Objetivo\n"
        "Documentar el flujo.\n"
        "## Alcance\n"
        "Incluye [COMPLETAR] y también [COMPLETAR].\n"
    )
    slots = pending.find_pending(md)
    assert len(slots) == 3
    assert slots[0].section == "Datos generales"
    assert slots[2].section == "Alcance"


def test_find_pending_sin_huecos_devuelve_vacio():
    assert pending.find_pending("## Objetivo\nTodo completo.\n") == []


def test_fill_pending_reemplaza_en_orden():
    md = "Responsable | [COMPLETAR]\nÁrea | [COMPLETAR]"
    out = pending.fill_pending(md, ["Juan Pérez", "Finanzas"])
    assert out == "Responsable | Juan Pérez\nÁrea | Finanzas"


def test_fill_pending_respuesta_vacia_deja_el_hueco():
    md = "Responsable | [COMPLETAR]\nÁrea | [COMPLETAR]"
    out = pending.fill_pending(md, ["Juan Pérez", ""])
    assert out == "Responsable | Juan Pérez\nÁrea | [COMPLETAR]"


def test_fill_pending_menos_respuestas_que_huecos():
    md = "a [COMPLETAR] b [COMPLETAR] c [COMPLETAR]"
    out = pending.fill_pending(md, ["X"])
    assert out == "a X b [COMPLETAR] c [COMPLETAR]"


def test_parse_questions_limpia_numeracion_y_ajusta_cantidad():
    raw = "1. ¿Quién es el responsable?\n2. ¿Cuál es el área?\n- ¿Y la fecha?"
    qs = pending.parse_questions(raw, 3)
    assert qs == ["¿Quién es el responsable?", "¿Cuál es el área?", "¿Y la fecha?"]


def test_parse_questions_rellena_si_faltan():
    qs = pending.parse_questions("¿Una sola?", 3)
    assert len(qs) == 3
    assert qs[0] == "¿Una sola?"


def test_parse_questions_trunca_si_sobran():
    qs = pending.parse_questions("una\ndos\ntres\ncuatro", 2)
    assert qs == ["una", "dos"]
