"""Tests del extractor de Power Query (lenguaje M) de Excel.

Construimos un .xlsx sintético con el blob DataMashup REAL (mismo formato
[MS-QDEFF] que genera Excel: versión + largo + ZIP interno con Formulas/Section1.m),
así probamos NUESTRO parseo del binario, no una librería externa.
"""
import base64
import struct
import zipfile
from io import BytesIO

from src.infrastructure.extractors.power_query import PowerQueryExtractor

_SECTION_M = (
    "section Section1;\n"
    "\n"
    'shared Ventas = let\n'
    '    Origen = Excel.CurrentWorkbook(){[Name="Tabla1"]}[Content],\n'
    '    Filtradas = Table.SelectRows(Origen, each [Monto] > 0)\n'
    "in\n"
    "    Filtradas;\n"
    "\n"
    'shared #"Clientes Activos" = let\n'
    '    Origen = Sql.Database("server", "db")\n'
    "in\n"
    "    Origen;\n"
)


def _mashup_b64(section_m: str) -> str:
    inner = BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("Formulas/Section1.m", section_m)
    opc = inner.getvalue()
    # versión (0) + largo del OPC + OPC + permisos (0): así lo arma Excel.
    blob = struct.pack("<I", 0) + struct.pack("<I", len(opc)) + opc + struct.pack("<I", 0)
    return base64.b64encode(blob).decode("ascii")


def _xlsx_with_pq(
    section_m: str = _SECTION_M, *, item_path: str = "customXml/item1.xml",
    encoding: str = "utf-8",
) -> bytes:
    xml = (
        '<DataMashup xmlns="http://schemas.microsoft.com/DataMashup">'
        f"{_mashup_b64(section_m)}</DataMashup>"
    )
    # Excel guarda ESTE item en UTF-16 con BOM; el resto del paquete es UTF-8. El
    # parámetro permite reproducir el caso real (ver test_item_en_utf16).
    item = xml.encode("utf-16") if encoding == "utf-16" else xml
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/workbook.xml", "<workbook/>")
        z.writestr(item_path, item)
    return buf.getvalue()


def _xlsx_sin_pq() -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/workbook.xml", "<workbook/>")
        z.writestr("customXml/item1.xml", "<props><titulo>x</titulo></props>")
    return buf.getvalue()


def test_read_component_devuelve_consultas():
    comp = PowerQueryExtractor().read_component(_xlsx_with_pq(), "reporte.xlsx")
    assert comp is not None
    assert comp.kind == "excel-powerquery"
    md = comp.summary_markdown
    assert "Ventas" in md
    assert "Clientes Activos" in md          # nombre con #"..." normalizado
    assert "Sql.Database" in md              # el código M va completo
    assert "```m" in md                       # el código en bloque m
    assert "2 consulta" in md                 # contó las dos consultas


def test_sin_datamashup_devuelve_none():
    assert PowerQueryExtractor().read_component(_xlsx_sin_pq(), "x.xlsx") is None


def test_no_zip_devuelve_none():
    # Defensivo: bytes que no son ZIP no deben explotar.
    assert PowerQueryExtractor().read_component(b"no soy zip", "x.xlsx") is None


def test_mashup_corrupto_devuelve_warning_sin_romper():
    item = (
        '<DataMashup xmlns="http://schemas.microsoft.com/DataMashup">'
        "###no-es-base64-valido###</DataMashup>"
    )
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("customXml/item1.xml", item)
    comp = PowerQueryExtractor().read_component(buf.getvalue(), "x.xlsx")
    # Detectó el DataMashup pero no pudo decodificar: avisa, no rompe.
    assert comp is not None
    assert comp.warnings


def test_encuentra_datamashup_en_xl_customxml():
    # Algunos libros guardan el item bajo xl/customXml/ en vez de customXml/.
    data = _xlsx_with_pq(item_path="xl/customXml/item1.xml")
    comp = PowerQueryExtractor().read_component(data, "x.xlsx")
    assert comp is not None
    assert "Ventas" in comp.summary_markdown


def test_item_en_utf16():
    # Regresión: Excel guarda el item del DataMashup en UTF-16 (BOM), no UTF-8.
    # Si se decodifica como UTF-8, el regex no matchea y Power Query se pierde
    # en silencio. Probado contra un .xlsm real generado por Excel.
    data = _xlsx_with_pq(item_path="customXml/item4.xml", encoding="utf-16")
    comp = PowerQueryExtractor().read_component(data, "real.xlsm")
    assert comp is not None
    assert "Ventas" in comp.summary_markdown
    assert "Clientes Activos" in comp.summary_markdown


def test_ignora_itemprops_que_solo_referencia_el_schema():
    # itemProps*.xml declara el schemaRef de DataMashup pero NO trae el blob.
    # No debe confundirse con el item real.
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "customXml/itemProps4.xml",
            '<ds:datastoreItem xmlns:ds="http://schemas.openxmlformats.org/'
            'officeDocument/2006/customXml"><ds:schemaRefs><ds:schemaRef '
            'ds:uri="http://schemas.microsoft.com/DataMashup"/></ds:schemaRefs>'
            "</ds:datastoreItem>",
        )
    assert PowerQueryExtractor().read_component(buf.getvalue(), "x.xlsx") is None
