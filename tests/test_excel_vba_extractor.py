"""Tests del extractor de macros VBA de Excel (.xlsm).

Mockeamos oletools/olevba: probamos NUESTRA lógica (detección, armado del
markdown, manejo de errores), no la librería. La verificación real contra un
.xlsm de verdad la hace el usuario.
"""
import sys
import types

import pytest

from src.domain.ports import UnsupportedPackageError
from src.infrastructure.extractors.excel_vba import ExcelVBAExtractor


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


def test_supports_detecta_vbaproject():
    ext = ExcelVBAExtractor()
    assert ext.supports(["xl/vbaProject.bin", "xl/workbook.xml"])
    assert not ext.supports(["xl/workbook.xml"])  # xlsx sin macros


def test_extract_arma_markdown_con_modulos(monkeypatch):
    _install_fake_olevba(monkeypatch, macros=[
        ("Module1", "Sub Foo()\n  MsgBox 1\nEnd Sub"),
        ("ThisWorkbook", "Private Sub Workbook_Open()\nEnd Sub"),
    ])
    r = ExcelVBAExtractor().extract(b"fake-bytes", "ventas.xlsm")
    assert r.kind == "excel-vba"
    assert r.name == "ventas"
    md = r.summary_markdown
    assert "Module1" in md and "ThisWorkbook" in md
    assert "MsgBox 1" in md
    assert "```vba" in md          # el código va en bloque vba
    assert "2 módulo" in md


def test_extract_ignora_modulos_vacios(monkeypatch):
    _install_fake_olevba(monkeypatch, macros=[("Vacio", "   "), ("Real", "Sub A()\nEnd Sub")])
    md = ExcelVBAExtractor().extract(b"x", "x.xlsm").summary_markdown
    assert "Real" in md
    assert "Vacio" not in md


def test_extract_sin_macros_falla(monkeypatch):
    _install_fake_olevba(monkeypatch, macros=[], has_macros=False)
    with pytest.raises(UnsupportedPackageError, match="macro"):
        ExcelVBAExtractor().extract(b"x", "x.xlsm")


def test_extract_macros_declaradas_pero_vacias_falla(monkeypatch):
    _install_fake_olevba(monkeypatch, macros=[("M", "  ")], has_macros=True)
    with pytest.raises(UnsupportedPackageError):
        ExcelVBAExtractor().extract(b"x", "x.xlsm")
