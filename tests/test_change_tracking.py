"""Fase 2: motor de diff entre dos importaciones del mismo paquete.

Lógica PURA de dominio (sin I/O): a partir de un snapshot guardado y un paquete
recién extraído, decide qué se DEPRECÓ, qué se MODIFICÓ y qué es NUEVO.
"""
from src.domain.change_tracking import ChangeStatus, PackageSnapshot, diff_package
from src.domain.entities import ExtractedPackage


def _sol(components, *, version="1.0.0.2", unique_name="Sol"):
    return ExtractedPackage(
        kind="power-platform-solution", name="Sol", summary_markdown="# Sol",
        components=components, version=version, unique_name=unique_name,
    )


def _comp(name, md, kind="power-automate-flow"):
    return ExtractedPackage(kind=kind, name=name, summary_markdown=md)


def test_snapshot_se_arma_desde_el_paquete():
    sol = _sol([_comp("F1", "# uno"), _comp("App", "# dos", "power-apps-canvas")])
    snap = PackageSnapshot.from_package(sol)
    assert snap.unique_name == "Sol"
    assert snap.version == "1.0.0.2"
    assert {c.name for c in snap.components} == {"F1", "App"}


def test_detecta_deprecado_modificado_nuevo_y_sin_cambios():
    # Versión anterior: F1, F2, F3
    viejo = PackageSnapshot.from_package(_sol(
        [_comp("F1", "# igual"), _comp("F2", "# viejo"), _comp("F3", "# se va")],
        version="1.0.0.1",
    ))
    # Versión nueva: F1 (igual), F2 (cambió), F4 (nuevo). F3 desapareció.
    nuevo = _sol(
        [_comp("F1", "# igual"), _comp("F2", "# NUEVO contenido"), _comp("F4", "# nuevo")],
        version="1.0.0.2",
    )
    r = diff_package(viejo, nuevo)

    assert r.deprecated == ["F3"]
    assert r.modified == ["F2"]
    assert r.added == ["F4"]
    assert r.unchanged == ["F1"]
    assert r.has_changes is True
    # Transición de versión queda registrada
    assert r.version_from == "1.0.0.1"
    assert r.version_to == "1.0.0.2"


def test_sin_cambios_no_reporta_nada():
    comps = [_comp("F1", "# a"), _comp("F2", "# b")]
    viejo = PackageSnapshot.from_package(_sol(comps, version="1.0.0.1"))
    nuevo = _sol([_comp("F1", "# a"), _comp("F2", "# b")], version="1.0.0.1")
    r = diff_package(viejo, nuevo)
    assert not r.deprecated and not r.modified and not r.added
    assert r.has_changes is False


def test_status_por_unidad_para_marcas_inline():
    viejo = PackageSnapshot.from_package(_sol([_comp("F1", "# a"), _comp("F2", "# b")]))
    nuevo = _sol([_comp("F1", "# a"), _comp("F2", "# CAMBIO"), _comp("F3", "# new")])
    r = diff_package(viejo, nuevo)
    # El render usa esto para poner ⚠/🔄/🆕 al lado de cada componente.
    assert r.status_of("F2") is ChangeStatus.MODIFIED
    assert r.status_of("F3") is ChangeStatus.ADDED
    assert r.status_of("F1") is ChangeStatus.UNCHANGED


def test_sin_snapshot_previo_todo_es_nuevo():
    # Primera importación: no hay con qué comparar → no hay diff (todo nuevo, sin ruido).
    nuevo = _sol([_comp("F1", "# a")])
    r = diff_package(None, nuevo)
    assert r.has_changes is False
    assert r.is_first_import is True
