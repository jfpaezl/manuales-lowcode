"""Tests del extractor de libros de Excel (compone VBA + Power Query).

El libro puede traer SOLO macros, SOLO Power Query, o LAS DOS. El extractor:
- las dos → paquete `excel-workbook` con un componente por tecnología (orquestador/obrero).
- una sola → degrada al paquete atómico de esa tecnología (preserva el comportamiento viejo).
- ninguna → UnsupportedPackageError con mensaje claro.

Mockeamos olevba (como en el test de VBA) y construimos el DataMashup real
(como en el test de Power Query).
"""
import sys
import types

import pytest

from src.domain.ports import UnsupportedPackageError
from src.infrastructure.extractors.excel import ExcelWorkbookExtractor
from tests.test_power_query_extractor import _xlsx_with_pq


def _install_fake_olevba(monkeypatch, *, macros, has_macros=True):
    class FakeParser:
        def __init__(self, filename="", data=None):
            pass

        def detect_vba_macros(self):
            return has_macros

        def extract_macros(self):
            for nombre, codigo in macros:
                yield ("f.xlsm", "VBA/x", nombre, codigo)

        def close(self):
            pass

    fake = types.ModuleType("oletools.olevba")
    fake.VBA_Parser = FakeParser
    monkeypatch.setitem(sys.modules, "oletools", types.ModuleType("oletools"))
    monkeypatch.setitem(sys.modules, "oletools.olevba", fake)


def test_supports_reconoce_vba_y_powerquery():
    ext = ExcelWorkbookExtractor()
    assert ext.supports(["xl/vbaProject.bin"])              # macros
    assert ext.supports(["customXml/item1.xml"])            # posible power query
    assert ext.supports(["xl/customXml/item2.xml"])
    assert not ext.supports(["xl/workbook.xml"])            # xlsx pelado


def test_solo_powerquery_degrada_a_paquete_atomico(monkeypatch):
    _install_fake_olevba(monkeypatch, macros=[], has_macros=False)
    r = ExcelWorkbookExtractor().extract(_xlsx_with_pq(), "reporte.xlsx")
    assert r.kind == "excel-powerquery"
    assert not r.components                                 # atómico
    assert "Ventas" in r.summary_markdown


def test_solo_vba_degrada_a_paquete_atomico(monkeypatch):
    _install_fake_olevba(monkeypatch, macros=[("Module1", "Sub Foo()\nEnd Sub")])
    # xlsm sin DataMashup → solo VBA
    import zipfile
    from io import BytesIO

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/vbaProject.bin", b"fake-ole")
    r = ExcelWorkbookExtractor().extract(buf.getvalue(), "ventas.xlsm")
    assert r.kind == "excel-vba"
    assert r.name == "ventas"                               # preserva identidad vieja
    assert not r.components


def test_vba_y_powerquery_arman_workbook_multicomponente(monkeypatch):
    _install_fake_olevba(monkeypatch, macros=[("Module1", "Sub Foo()\nEnd Sub")])
    # El mismo archivo trae vbaProject.bin Y el DataMashup de Power Query.
    import zipfile
    from io import BytesIO
    from tests.test_power_query_extractor import _mashup_b64, _SECTION_M

    item = (
        '<DataMashup xmlns="http://schemas.microsoft.com/DataMashup">'
        f"{_mashup_b64(_SECTION_M)}</DataMashup>"
    )
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/vbaProject.bin", b"fake-ole")
        z.writestr("customXml/item1.xml", item)
    r = ExcelWorkbookExtractor().extract(buf.getvalue(), "panel.xlsm")

    assert r.kind == "excel-workbook"
    kinds = [c.kind for c in r.components]
    assert "excel-vba" in kinds
    assert "excel-powerquery" in kinds
    # Los nombres de componente deben ser DISTINTOS (el diff los keya por nombre).
    nombres = [c.name for c in r.components]
    assert len(set(nombres)) == len(nombres)
    assert r.unique_name == "panel"


def test_ni_macros_ni_powerquery_falla(monkeypatch):
    _install_fake_olevba(monkeypatch, macros=[], has_macros=False)
    import zipfile
    from io import BytesIO

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("customXml/item1.xml", "<props/>")     # customXml sin DataMashup
    with pytest.raises(UnsupportedPackageError):
        ExcelWorkbookExtractor().extract(buf.getvalue(), "vacio.xlsx")
