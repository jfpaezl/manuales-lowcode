"""Tests del extractor de paquetes de Power Automate (export individual).

Armamos ZIPs en memoria que replican la estructura REAL del paquete que
genera Power Automate al exportar un flujo fuera de una Solution:

    manifest.json
    Microsoft.Flow/flows/<guid>/definition.json

El definition.json lleva la lógica en properties.definition.{triggers,actions}.
"""
import io
import json
import zipfile

import pytest

from src.domain.ports import UnsupportedPackageError
from src.infrastructure.extractors.power_automate import PowerAutomateFlowExtractor


def _zip(files: dict[str, str]) -> bytes:
    """Empaqueta {ruta: contenido} en un ZIP y devuelve los bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    return buf.getvalue()


def _flow_zip(display_name: str, definition: dict, *, guid: str = "abc-123") -> bytes:
    pkg = {
        "name": guid,
        "type": "Microsoft.Flow/flows",
        "properties": {"displayName": display_name, "definition": definition},
    }
    return _zip(
        {
            "manifest.json": json.dumps({"schema": "1.0"}),
            f"Microsoft.Flow/flows/{guid}/definition.json": json.dumps(pkg),
        }
    )


# --- Casos felices --------------------------------------------------------

def test_extrae_nombre_y_trigger():
    definition = {
        "triggers": {
            "Cuando_se_crea_un_elemento": {
                "type": "OpenApiConnection",
                "inputs": {"host": {"operationId": "GetOnCreatedItems"}},
            }
        },
        "actions": {},
    }
    pkg = _flow_zip("Aprobación de facturas", definition)

    result = PowerAutomateFlowExtractor().extract(pkg, "factura.zip")

    assert result.kind == "power-automate-flow"
    assert result.name == "Aprobación de facturas"
    assert "Cuando se crea un elemento" in result.summary_markdown
    assert "GetOnCreatedItems" in result.summary_markdown


def test_lista_acciones_en_orden_de_ejecucion():
    # En el JSON el orden está desordenado a propósito: Enviar va DESPUÉS de Obtener,
    # según runAfter. El extractor debe reordenarlas por dependencia, no por dict.
    definition = {
        "triggers": {"Manual": {"type": "Request"}},
        "actions": {
            "Enviar_correo": {
                "type": "OpenApiConnection",
                "inputs": {"host": {"operationId": "SendEmailV2"}},
                "runAfter": {"Obtener_elementos": ["Succeeded"]},
            },
            "Obtener_elementos": {
                "type": "OpenApiConnection",
                "inputs": {"host": {"operationId": "GetItems"}},
                "runAfter": {},
            },
        },
    }
    md = PowerAutomateFlowExtractor().extract(_flow_zip("Flujo", definition)).summary_markdown

    assert md.index("Obtener elementos") < md.index("Enviar correo")


def test_recursa_en_condiciones():
    definition = {
        "triggers": {"Manual": {"type": "Request"}},
        "actions": {
            "Condicion": {
                "type": "If",
                "runAfter": {},
                "actions": {
                    "Aprobar": {"type": "OpenApiConnection",
                                "inputs": {"host": {"operationId": "Approve"}}}
                },
                "else": {
                    "actions": {
                        "Rechazar": {"type": "OpenApiConnection",
                                     "inputs": {"host": {"operationId": "Reject"}}}
                    }
                },
            }
        },
    }
    md = PowerAutomateFlowExtractor().extract(_flow_zip("Flujo", definition)).summary_markdown

    assert "Condicion" in md
    assert "Aprobar" in md
    assert "Rechazar" in md
    # Lo anidado debe quedar más indentado que el contenedor
    assert "  - **Aprobar**" in md or "    - **Aprobar**" in md


def test_recursa_en_foreach():
    definition = {
        "triggers": {"Manual": {"type": "Request"}},
        "actions": {
            "Para_cada": {
                "type": "Foreach",
                "runAfter": {},
                "actions": {
                    "Crear_archivo": {"type": "OpenApiConnection",
                                      "inputs": {"host": {"operationId": "CreateFile"}}}
                },
            }
        },
    }
    md = PowerAutomateFlowExtractor().extract(_flow_zip("Flujo", definition)).summary_markdown
    assert "Para cada" in md
    assert "Crear archivo" in md


def test_trigger_de_notificacion_se_lee_legible_y_con_operacion():
    # Caso REAL: trigger "When a new email arrives (V3)" es OpenApiConnectionNotification.
    definition = {
        "triggers": {
            "When_a_new_email_arrives_V3": {
                "type": "OpenApiConnectionNotification",
                "inputs": {"host": {
                    "operationId": "OnNewEmailV3",
                    "apiId": "/providers/Microsoft.PowerApps/apis/shared_office365",
                    "connectionName": "shared_office365",
                }},
            }
        },
        "actions": {},
    }
    md = PowerAutomateFlowExtractor().extract(_flow_zip("Flujo", definition)).summary_markdown
    assert "OnNewEmailV3" in md            # extrae la operación del trigger
    assert "Conector" in md                # tipo legible, no el crudo
    assert "OpenApiConnectionNotification" not in md
    # El apiId largo es ruido: NO debe aparecer
    assert "/providers/" not in md


def test_orden_en_cadena_larga_de_runafter():
    # Cadena real: Filter -> Initialize -> Foreach -> Send. Desordenadas en el dict.
    definition = {
        "triggers": {"T": {"type": "Request"}},
        "actions": {
            "Foreach": {"type": "Foreach", "actions": {}, "runAfter": {"Initialize": ["Succeeded"]}},
            "Initialize": {"type": "InitializeVariable", "runAfter": {"Filter": ["Succeeded"]}},
            "Send": {"type": "OpenApiConnection", "runAfter": {"Foreach": ["Succeeded"]}},
            "Filter": {"type": "Query", "runAfter": {}},
        },
    }
    md = PowerAutomateFlowExtractor().extract(_flow_zip("Flujo", definition)).summary_markdown
    assert md.index("Filter") < md.index("Initialize") < md.index("Foreach") < md.index("Send")


# --- Defensivo: distintas ubicaciones del workflow ------------------------

def test_workflow_directo_en_definition_sin_properties():
    # Algunos exports traen el definition.json con triggers/actions en la raíz.
    raw = {"$schema": "x", "triggers": {"T": {"type": "Request"}}, "actions": {}}
    pkg = _zip({"Microsoft.Flow/flows/x/definition.json": json.dumps(raw)})
    result = PowerAutomateFlowExtractor().extract(pkg, "flujo.zip")
    # Sin displayName, cae al nombre del archivo del zip
    assert result.kind == "power-automate-flow"
    assert "T" in result.summary_markdown


# --- Errores claros -------------------------------------------------------

def test_zip_sin_definition_falla():
    pkg = _zip({"manifest.json": "{}", "otra/cosa.txt": "nada"})
    with pytest.raises(UnsupportedPackageError, match="definition.json"):
        PowerAutomateFlowExtractor().extract(pkg, "x.zip")


def test_archivo_no_zip_falla():
    with pytest.raises(UnsupportedPackageError, match="ZIP"):
        PowerAutomateFlowExtractor().extract(b"esto no es un zip", "x.zip")
