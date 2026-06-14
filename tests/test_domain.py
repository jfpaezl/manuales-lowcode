from src.domain.entities import (
    Manual,
    ManualType,
    ManualVersion,
    Section,
)


def _manual() -> Manual:
    return Manual(title="Macro de facturación", type=ManualType.TECNICO, category="Macros")


def test_manual_sin_versiones_arranca_en_v1():
    m = _manual()
    assert m.latest_version is None
    assert m.next_version_number() == 1


def test_next_version_incrementa_sobre_la_ultima():
    m = _manual()
    m.versions = [
        ManualVersion(version=1, content_html="<p>a</p>"),
        ManualVersion(version=2, content_html="<p>b</p>"),
    ]
    assert m.latest_version.version == 2
    assert m.next_version_number() == 3


def test_content_hash_cambia_con_el_contenido():
    v1 = ManualVersion(version=1, content_html="<p>a</p>")
    v2 = ManualVersion(version=1, content_html="<p>b</p>")
    assert v1.content_hash != v2.content_hash


def test_seccion_guarda_orden():
    s = Section(title="Intro", content_html="<p>hola</p>", order=2)
    assert s.order == 2
