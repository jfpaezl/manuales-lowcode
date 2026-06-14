"""Tests del extractor de Soluciones de Power Platform.

Una Solution trae flujos como Workflows/*.json sueltos (con la lógica en
properties.definition) y canvas apps como CanvasApps/*.msapp. El extractor
recorre todo y delega a los extractores de flow y canvas ya existentes.
"""
import io
import json
import zipfile

import pytest

from src.domain.ports import UnsupportedPackageError
from src.infrastructure.extractors.solution import SolutionExtractor

_SOLUTION_XML = (
    '<?xml version="1.0"?><ImportExportXml><SolutionManifest>'
    "<UniqueName>CentralizadorFondosPer</UniqueName>"
    '<LocalizedNames><LocalizedName description="Centralizador Fondos Perú" '
    'languagecode="1033" /></LocalizedNames>'
    "<Version>1.0.0.1</Version>"
    "</SolutionManifest></ImportExportXml>"
)


def _msapp_bytes(app_name: str = "MiApp") -> bytes:
    screen = (
        "Screens:\n  Inicio:\n    Children:\n"
        "      - Boton1:\n          Control: Button@2.2.0\n"
        '          Properties:\n            Text: ="Hola"\n'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Header.json", "{}")
        zf.writestr("Properties.json", json.dumps({"Name": app_name}))
        zf.writestr("References/DataSources.json", json.dumps({"DataSources": []}))
        zf.writestr("Src/Inicio.pa.yaml", screen)
    return buf.getvalue()


def _flow_json(trigger_type: str = "Request") -> str:
    return json.dumps({
        "schemaVersion": "1.0.0.0",
        "properties": {
            "definition": {
                "triggers": {"manual": {"type": trigger_type}},
                "actions": {"Enviar_correo": {
                    "type": "OpenApiConnection",
                    "inputs": {"host": {"operationId": "SendEmailV2"}},
                    "runAfter": {},
                }},
            }
        },
    })


def _solution_zip(*, flows: int = 2, apps: int = 1) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("solution.xml", _SOLUTION_XML)
        zf.writestr("customizations.xml", "<x/>")
        zf.writestr("[Content_Types].xml", "<x/>")
        for i in range(flows):
            zf.writestr(f"Workflows/Flujo{i}-0BFDE794-DDE4-EF11-9341-0022482A1116.json", _flow_json())
        for i in range(apps):
            zf.writestr(f"CanvasApps/app{i}_DocumentUri.msapp", _msapp_bytes(f"App{i}"))
    return buf.getvalue()


# --- Casos felices --------------------------------------------------------

def test_extrae_nombre_y_version_de_la_solucion():
    r = SolutionExtractor().extract(_solution_zip(), "sol.zip")
    assert r.kind == "power-platform-solution"
    assert r.name == "Centralizador Fondos Perú"
    assert "1.0.0.1" in r.summary_markdown


def test_incluye_flujos_y_apps_delegando_a_los_extractores():
    r = SolutionExtractor().extract(_solution_zip(flows=2, apps=1), "sol.zip")
    md = r.summary_markdown
    assert r.warnings == []
    # Resumen de cantidades
    assert "2 flujo(s)" in md and "1 app(s)" in md
    # Contenido de los flujos (delegado a PowerAutomate)
    assert "Flujo de Power Automate" in md
    assert "SendEmailV2" in md
    # Contenido de la app (delegado a PowerApps)
    assert "Aplicación Power Apps" in md
    assert "App0" in md
    assert "Hola" in md  # control de la pantalla


def test_nombre_de_flujo_sin_guid():
    md = SolutionExtractor().extract(_solution_zip(flows=1, apps=0), "sol.zip").summary_markdown
    assert "Flujo0" in md
    assert "0BFDE794" not in md  # el GUID del archivo no aparece


def test_solucion_vacia_avisa():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("solution.xml", _SOLUTION_XML)
    r = SolutionExtractor().extract(buf.getvalue(), "sol.zip")
    assert any("no tenía" in w.lower() for w in r.warnings)


# --- Detección ------------------------------------------------------------

def test_supports_reconoce_solucion():
    ext = SolutionExtractor()
    assert ext.supports(["solution.xml", "Workflows/x.json"])
    assert not ext.supports(["Microsoft.Flow/flows/1/definition.json"])
    assert not ext.supports(["Header.json", "Src/Inicio.pa.yaml"])


# --- Errores --------------------------------------------------------------

def test_sin_solution_xml_falla():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("otra.xml", "<x/>")
    with pytest.raises(UnsupportedPackageError, match="solution.xml"):
        SolutionExtractor().extract(buf.getvalue(), "x.zip")


def test_archivo_no_zip_falla():
    with pytest.raises(UnsupportedPackageError, match="ZIP"):
        SolutionExtractor().extract(b"no soy zip", "x.zip")
