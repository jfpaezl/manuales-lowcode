"""Fase 1 del seguimiento de cambios: ExtractedPackage como materia prima
diffeable (huella + unidades + identidad/versión)."""
from src.domain.entities import ExtractedPackage


def test_fingerprint_estable_y_sensible_al_contenido():
    a = ExtractedPackage(kind="x", name="N", summary_markdown="# A\n- paso")
    b = ExtractedPackage(kind="x", name="N", summary_markdown="# A\n- paso")
    c = ExtractedPackage(kind="x", name="N", summary_markdown="# A\n- paso CAMBIADO")
    # Mismo contenido → misma huella; contenido distinto → huella distinta.
    assert a.fingerprint == b.fingerprint
    assert a.fingerprint != c.fingerprint


def test_diff_units_de_paquete_atomico_es_el_paquete_mismo():
    # Un flujo suelto / macro sin sub-componentes: la unidad es el paquete entero.
    pkg = ExtractedPackage(kind="power-automate-flow", name="Flujo", summary_markdown="# F")
    units = pkg.diff_units
    assert len(units) == 1
    assert units[0].name == "Flujo"


def test_diff_units_de_solucion_son_sus_componentes():
    c1 = ExtractedPackage(kind="power-automate-flow", name="Flujo1", summary_markdown="# F1")
    c2 = ExtractedPackage(kind="power-apps-canvas", name="App1", summary_markdown="# A1")
    sol = ExtractedPackage(
        kind="power-platform-solution", name="Sol", summary_markdown="# Sol",
        components=[c1, c2],
    )
    units = sol.diff_units
    assert [u.name for u in units] == ["Flujo1", "App1"]


def test_campos_de_identidad_y_version_por_defecto_vacios():
    pkg = ExtractedPackage(kind="x", name="N", summary_markdown="x")
    assert pkg.version == ""
    assert pkg.unique_name == ""
