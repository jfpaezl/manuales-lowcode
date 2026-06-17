"""Tests del extractor de canvas apps de Power Apps (.msapp).

Replicamos la estructura REAL del export:
  - ZIP externo (paquete) con un .msapp anidado bajo Microsoft.PowerApps/apps/<id>/
  - el .msapp es OTRO zip con Properties.json, References/DataSources.json y Src/*.pa.yaml

Las pantallas viven en Src/*.pa.yaml como árbol Screens -> control -> Children.
"""
import io
import json
import zipfile

import pytest

from src.domain.ports import UnsupportedPackageError
from src.infrastructure.extractors.power_apps import PowerAppsCanvasExtractor

_SCREEN_YAML = """\
Screens:
  Inicio:
    Properties:
      Fill: =RGBA(0,0,0,1)
      OnVisible: |-
        =Set(
            MenuID,
            1
        );
    Children:
      - Container2:
          Control: GroupContainer@1.3.0
          Variant: AutoLayout
          Properties:
            LayoutDirection: =LayoutDirection.Horizontal
            Width: =Parent.Width
          Children:
            - Boton1:
                Control: Button@2.2.0
                Properties:
                  Color: =RGBA(1,1,1,1)
                  Text: ="Guardar"
                  OnSelect: |-
                    =Patch(Registros, Defaults(Registros), {Nombre: txt.Text})
            - Menu1:
                Control: CanvasComponent
                ComponentName: JF_sideMenu
                Properties:
                  Width: =65
"""


def _msapp_bytes(*, app_name: str = "MiApp", screens_yaml: str = _SCREEN_YAML,
                 data_sources: list[dict] | None = None) -> bytes:
    ds = {"DataSources": data_sources if data_sources is not None else [
        {"Name": "Office365Outlook", "Type": "ServiceInfo"},
        {"Name": "CustomGallerySample", "Type": "StaticDataSourceInfo"},
    ]}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Header.json", json.dumps({"DocVersion": "1.0"}))
        zf.writestr("Properties.json", json.dumps({"Name": app_name}))
        zf.writestr("References/DataSources.json", json.dumps(ds))
        zf.writestr("Src/Inicio.pa.yaml", screens_yaml)
        zf.writestr("Src/_EditorState.pa.yaml", "ignorar: esto")
    return buf.getvalue()


def _package_zip(msapp: bytes) -> bytes:
    """Envuelve el .msapp dentro del ZIP de paquete, como hace el export real."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", "{}")
        zf.writestr("Microsoft.PowerApps/apps/123/123.json", "{}")
        zf.writestr("Microsoft.PowerApps/apps/123/Nef-document.msapp", msapp)
    return buf.getvalue()


# --- Casos felices --------------------------------------------------------

def test_extrae_nombre_app_y_fuentes_de_datos():
    pkg = _package_zip(_msapp_bytes(app_name="PlantillaCentralizadores"))
    r = PowerAppsCanvasExtractor().extract(pkg, "pruebapowerapps.zip")
    assert r.kind == "power-apps-canvas"
    assert r.name == "PlantillaCentralizadores"
    assert "Office365Outlook" in r.summary_markdown
    assert "CustomGallerySample" in r.summary_markdown


def test_fuente_conectada_muestra_sitio_lista_y_flujos():
    # Caso REAL: una app que llama a varios flujos (shared_logicflows) y además
    # tiene fuentes SharePoint/Excel directas con la RUTA en DatasetName/TableName.
    data_sources = [
        {"Name": "CentralizadorPerApps", "Type": "ServiceInfo",
         "ApiId": "/providers/microsoft.powerapps/apis/shared_logicflows"},
        {"Name": "Centralizador Peru", "Type": "ConnectedDataSourceInfo",
         "ApiId": "/providers/microsoft.powerapps/apis/shared_sharepointonline",
         "DatasetName": "https://contoso.sharepoint.com/sites/Ops",
         "TableName": "41d3f30f-6653-4e61-bafe-087e2724e9c0"},
        {"Name": "CodigoFondos", "Type": "ConnectedDataSourceInfo",
         "ApiId": "/providers/microsoft.powerapps/apis/shared_excelonlinebusiness",
         "DatasetName": "https%253A%252F%252Fcontoso.sharepoint.com%252Fsites%252FFondos",
         "TableName": "{7BBDA6E1-3E6F-456A-A205-7E942FFCD27B}"},
    ]
    pkg = _package_zip(_msapp_bytes(data_sources=data_sources))
    md = PowerAppsCanvasExtractor().extract(pkg, "app.zip").summary_markdown
    # El flujo conectado se reconoce como tal (app con varios Power Automate).
    assert "CentralizadorPerApps — flujo de Power Automate" in md
    # La ruta de SharePoint aparece (sitio + lista), no [COMPLETAR].
    assert "https://contoso.sharepoint.com/sites/Ops" in md
    assert "41d3f30f-6653-4e61-bafe-087e2724e9c0" in md
    assert "SharePoint" in md
    # El sitio de Excel venía doble-encodeado: debe verse legible.
    assert "https://contoso.sharepoint.com/sites/Fondos" in md
    assert "Excel Online" in md


def test_lista_pantalla_y_jerarquia_de_controles():
    r = PowerAppsCanvasExtractor().extract(_package_zip(_msapp_bytes()), "x.zip")
    md = r.summary_markdown
    assert "Pantalla: Inicio" in md
    assert "Container2" in md and "Boton1" in md and "Menu1" in md
    # El control hijo queda más indentado que el contenedor
    assert md.index("Container2") < md.index("Boton1")
    assert "  " in md  # hay indentación de jerarquía


def test_muestra_tipo_de_control_sin_version():
    md = PowerAppsCanvasExtractor().extract(_package_zip(_msapp_bytes()), "x.zip").summary_markdown
    assert "Button" in md
    assert "Button@2.2.0" not in md  # la versión @2.2.0 es ruido, se quita


def test_incluye_formulas_de_comportamiento_y_no_de_estilo():
    md = PowerAppsCanvasExtractor().extract(_package_zip(_msapp_bytes()), "x.zip").summary_markdown
    # Comportamiento / contenido: SÍ
    assert "OnSelect" in md and "Patch(Registros" in md
    assert "Guardar" in md  # Text
    assert "Set(" in md and "MenuID" in md  # OnVisible de la pantalla
    # Estilo puro: NO (ruido)
    assert "RGBA" not in md
    assert "Color" not in md


def test_anota_direccion_de_layout_y_componente():
    md = PowerAppsCanvasExtractor().extract(_package_zip(_msapp_bytes()), "x.zip").summary_markdown
    assert "horizontal" in md.lower()          # LayoutDirection del contenedor
    assert "JF_sideMenu" in md                 # componente referenciado


def test_tolera_formula_vacia_signo_igual_suelto():
    # Power Apps escribe propiedades vacías como `Prop: =`. PyYAML interpreta el
    # `=` suelto como un tag legacy y explota: el extractor debe tolerarlo.
    yaml_con_igual = (
        "Screens:\n"
        "  Inicio:\n"
        "    Children:\n"
        "      - Boton1:\n"
        "          Control: Button@2.2.0\n"
        "          Properties:\n"
        "            DisplayMode: =\n"
        "            Text: =\"Hola\"\n"
    )
    r = PowerAppsCanvasExtractor().extract(
        _package_zip(_msapp_bytes(screens_yaml=yaml_con_igual)), "x.zip"
    )
    assert r.warnings == []                 # NO debe haber error de parseo
    assert "Boton1" in r.summary_markdown
    assert "Hola" in r.summary_markdown


def test_msapp_directo_sin_envoltorio_de_paquete():
    # Defensivo: si nos dan el .msapp crudo (no el paquete), también funciona.
    r = PowerAppsCanvasExtractor().extract(_msapp_bytes(app_name="Directa"), "app.msapp")
    assert r.name == "Directa"
    assert "Pantalla: Inicio" in r.summary_markdown


# --- Detección (para el dispatcher) ---------------------------------------

def test_supports_reconoce_paquete_y_msapp_directo():
    ext = PowerAppsCanvasExtractor()
    assert ext.supports(["Microsoft.PowerApps/apps/1/x-document.msapp", "manifest.json"])
    assert ext.supports(["Header.json", "Properties.json", "Src/Inicio.pa.yaml"])
    assert not ext.supports(["Microsoft.Flow/flows/1/definition.json"])


# --- Errores claros -------------------------------------------------------

def test_zip_sin_msapp_falla():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", "{}")
    with pytest.raises(UnsupportedPackageError):
        PowerAppsCanvasExtractor().extract(buf.getvalue(), "x.zip")


def test_archivo_no_zip_falla():
    with pytest.raises(UnsupportedPackageError, match="ZIP"):
        PowerAppsCanvasExtractor().extract(b"no soy un zip", "x.zip")
