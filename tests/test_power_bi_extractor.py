"""Tests del extractor de Power BI (.pbit / .pbix).

Construimos un .pbit sintético con el DataModelSchema y el Report/Layout en
UTF-16 LE SIN BOM (igual que Power BI real), así probamos NUESTRO parseo: la
detección de encoding, el filtrado de tablas de fecha automáticas, la extracción
de medidas DAX / M y de los visuales.
"""
import json
import zipfile
from io import BytesIO

import pytest

from src.domain.ports import UnsupportedPackageError
from src.infrastructure.extractors.power_bi import PowerBIExtractor

_MODEL = {
    "compatibilityLevel": 1567,
    "model": {
        "tables": [
            {
                "name": "Ventas",
                "columns": [
                    {"name": "Monto", "dataType": "double"},
                    {"name": "Rango", "type": "calculated", "dataType": "string",
                     "expression": ["SWITCH ( TRUE (),", "  [Monto] > 0, \"pos\" )"]},
                ],
                "measures": [
                    {"name": "Total Ventas", "formatString": "0",
                     "expression": ["SUM ( 'Ventas'[Monto] )"]},
                ],
                "partitions": [
                    {"name": "Ventas-p", "mode": "import",
                     "source": {"type": "m", "expression": [
                         "let",
                         '    Origen = Excel.Workbook(Web.Contents("https://contoso/v.xlsx"))',
                         "in Origen"]}},
                ],
            },
            # Tabla de fecha automática: NO debe documentarse.
            {"name": "LocalDateTable_abc123", "isHidden": True,
             "columns": [{"name": "Date", "dataType": "dateTime"}], "partitions": []},
        ],
        "relationships": [
            # Esta apunta a la tabla de fecha auto → se filtra.
            {"fromTable": "Ventas", "fromColumn": "Fecha",
             "toTable": "LocalDateTable_abc123", "toColumn": "Date"},
            # Esta es real → se conserva.
            {"fromTable": "Ventas", "fromColumn": "ClienteId",
             "toTable": "Clientes", "toColumn": "Id", "isActive": True},
        ],
    },
}

_LAYOUT = {
    "id": 0,
    "sections": [
        {"displayName": "Resumen", "visualContainers": [
            {"config": json.dumps({"singleVisual": {
                "visualType": "cardVisual",
                "projections": {"Data": [{"queryRef": "Ventas.Total Ventas"}]}}})},
            {"config": json.dumps({"singleVisual": {
                "visualType": "slicer",
                "projections": {"Values": [{"queryRef": "Ventas.Rango"}]}}})},
            {"config": json.dumps({"singleVisual": {"visualType": "textbox"}})},
        ]},
    ],
}


def _pbit(*, model=_MODEL, layout=_LAYOUT, with_model=True, with_report=True,
          compressed_model=False) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Version", "3.0")
        if with_model:
            # Power BI escribe en UTF-16 LE SIN BOM: ese es el caso a reproducir.
            z.writestr("DataModelSchema", json.dumps(model).encode("utf-16-le"))
        if compressed_model:
            z.writestr("DataModel", b"\x00\x01\x02 binario comprimido")
        if with_report:
            z.writestr("Report/Layout", json.dumps(layout).encode("utf-16-le"))
    return buf.getvalue()


def test_supports_reconoce_pbit():
    ext = PowerBIExtractor()
    assert ext.supports(["DataModelSchema", "Report/Layout", "Version"])
    assert ext.supports(["Report/Layout"])
    assert not ext.supports(["xl/workbook.xml"])


def test_modelo_y_reporte_arman_paquete_multicomponente():
    r = PowerBIExtractor().extract(_pbit(), "Control v4.pbit")
    assert r.kind == "power-bi"
    kinds = [c.kind for c in r.components]
    assert "power-bi-model" in kinds and "power-bi-report" in kinds
    nombres = [c.name for c in r.components]
    assert len(set(nombres)) == len(nombres)   # distintos (para el diff)
    assert r.unique_name == "Control v4"


def test_modelo_extrae_medidas_dax_y_origen_m():
    r = PowerBIExtractor().extract(_pbit(), "x.pbit")
    md = [c for c in r.components if c.kind == "power-bi-model"][0].summary_markdown
    assert "**Total Ventas**" in md
    assert "SUM ( 'Ventas'[Monto] )" in md      # DAX de la medida
    assert "```dax" in md
    assert "Excel.Workbook" in md               # origen M de la partición
    assert "https://contoso/v.xlsx" in md
    assert "```m" in md


def test_columna_calculada_con_dax():
    r = PowerBIExtractor().extract(_pbit(), "x.pbit")
    md = [c for c in r.components if c.kind == "power-bi-model"][0].summary_markdown
    assert "Rango" in md
    assert "calculada" in md
    assert "SWITCH ( TRUE ()" in md


def test_filtra_tablas_de_fecha_automaticas():
    r = PowerBIExtractor().extract(_pbit(), "x.pbit")
    model = [c for c in r.components if c.kind == "power-bi-model"][0]
    md = model.summary_markdown
    assert "LocalDateTable_abc123" not in md          # tabla auto: fuera
    assert "1 tabla(s)" in md                          # solo Ventas
    # La relación a la tabla auto se filtra; queda solo la real (Clientes).
    assert "1 relación(es)" in md
    assert "Clientes" in md


def test_reporte_lista_paginas_y_visuales():
    r = PowerBIExtractor().extract(_pbit(), "x.pbit")
    md = [c for c in r.components if c.kind == "power-bi-report"][0].summary_markdown
    assert "Página: Resumen" in md
    assert "Tarjeta" in md                             # cardVisual legible
    assert "Ventas.Total Ventas" in md                 # campo del visual
    assert "Segmentación (slicer)" in md
    assert "Cuadro de texto" in md                     # visual sin campos, igual listado


def test_solo_reporte_degrada_y_avisa_que_falta_pbit():
    # Caso .pbix: hay reporte pero el modelo viene comprimido (DataModel, no schema).
    data = _pbit(with_model=False, compressed_model=True)
    r = PowerBIExtractor().extract(data, "informe.pbix")
    assert r.kind == "power-bi-report"                 # atómico, no multicomponente
    assert not r.components
    assert any("pbit" in w.lower() for w in r.warnings)  # avisa cómo exportar bien


def test_archivo_no_zip_falla():
    with pytest.raises(UnsupportedPackageError, match="ZIP"):
        PowerBIExtractor().extract(b"no soy zip", "x.pbit")
