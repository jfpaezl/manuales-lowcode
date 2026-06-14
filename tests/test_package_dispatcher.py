"""Tests del dispatcher: enruta cada ZIP al extractor que lo reconoce."""
import io
import json
import zipfile

import pytest

from src.domain.ports import UnsupportedPackageError
from src.infrastructure.extractors.dispatcher import CompositePackageExtractor
from src.infrastructure.extractors.power_apps import PowerAppsCanvasExtractor
from src.infrastructure.extractors.power_automate import PowerAutomateFlowExtractor
from src.infrastructure.extractors.solution import SolutionExtractor


def _flow_zip() -> bytes:
    pkg = {"properties": {"displayName": "Mi Flujo",
                          "definition": {"triggers": {"T": {"type": "Request"}}, "actions": {}}}}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Microsoft.Flow/flows/g/definition.json", json.dumps(pkg))
    return buf.getvalue()


def _powerapps_zip() -> bytes:
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as zf:
        zf.writestr("Header.json", "{}")
        zf.writestr("Properties.json", json.dumps({"Name": "MiApp"}))
        zf.writestr("Src/Inicio.pa.yaml", "Screens:\n  Inicio:\n    Children: []\n")
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as zf:
        zf.writestr("Microsoft.PowerApps/apps/1/x-document.msapp", inner.getvalue())
    return outer.getvalue()


def _solution_zip() -> bytes:
    """Solution con un .msapp adentro: debe ir a Solution, NO a Power Apps."""
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as zf:
        zf.writestr("Header.json", "{}")
        zf.writestr("Properties.json", json.dumps({"Name": "App"}))
        zf.writestr("Src/Inicio.pa.yaml", "Screens:\n  Inicio:\n    Children: []\n")
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as zf:
        zf.writestr("solution.xml", "<x><Version>1.0</Version></x>")
        zf.writestr("CanvasApps/app_DocumentUri.msapp", inner.getvalue())
    return outer.getvalue()


@pytest.fixture
def dispatcher() -> CompositePackageExtractor:
    return CompositePackageExtractor([
        SolutionExtractor(),
        PowerAutomateFlowExtractor(),
        PowerAppsCanvasExtractor(),
    ])


def test_enruta_solucion_aunque_tenga_msapp(dispatcher):
    # Una Solution tiene .msapp adentro, pero debe ganar Solution (va primero).
    r = dispatcher.extract(_solution_zip(), "sol.zip")
    assert r.kind == "power-platform-solution"


def test_enruta_flujo_a_power_automate(dispatcher):
    r = dispatcher.extract(_flow_zip(), "flujo.zip")
    assert r.kind == "power-automate-flow"
    assert r.name == "Mi Flujo"


def test_enruta_canvas_a_power_apps(dispatcher):
    r = dispatcher.extract(_powerapps_zip(), "app.zip")
    assert r.kind == "power-apps-canvas"
    assert r.name == "MiApp"


def test_paquete_desconocido_falla_claro(dispatcher):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("cualquier/cosa.txt", "nada")
    with pytest.raises(UnsupportedPackageError, match="recono"):
        dispatcher.extract(buf.getvalue(), "raro.zip")


def test_archivo_no_zip_falla(dispatcher):
    with pytest.raises(UnsupportedPackageError, match="ZIP"):
        dispatcher.extract(b"no soy un zip", "x.zip")
