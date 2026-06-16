"""Paquetes de conocimiento de dominio por tecnología.

¿Qué problema resuelven? La IA de la app sabe redactar, pero no necesariamente
sabe QUÉ tiene que cubrir un buen manual de —digamos— una tabla de Dataverse
(columnas, claves, relaciones, permisos, configuración). Estos «knowledge packs»
le inyectan ESE conocimiento al prompt, indexado por el `kind` del componente.

Importante: esto vive DENTRO de la app a propósito. La IA que genera los manuales
corre en otro proceso y no puede leer las SKILL.md de Claude Code; para que mejore
LO QUE GENERA, el conocimiento tiene que viajar en el prompt. Una cosa por archivo:
agregar una tecnología nueva = agregar un módulo y registrarlo acá."""
from __future__ import annotations

from . import dataverse, excel_vba, power_apps, power_automate, solution

# Registro: kind del componente → guía de qué documentar y cómo.
_REGISTRY: dict[str, str] = {}
for _mod in (power_automate, power_apps, excel_vba, dataverse, solution):
    _REGISTRY.update(_mod.GUIDANCE)


def knowledge_for(kind: str) -> str:
    """Guía de dominio para ese tipo de componente. "" si no hay pack (la IA
    sigue funcionando, solo sin la ayuda extra)."""
    return _REGISTRY.get(kind, "")


# Para los modos SIN paquete (generar desde tema, documentar código, transcripción)
# no hay `kind`: enrutamos por palabras clave del texto de la categoría/hint al pack
# que corresponda. El orden importa: lo más específico primero.
_CATEGORY_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("dataverse", "tabla", "entidad", "cds"), "dataverse-table"),
    (("power automate", "powerautomate", "flujo", "flow"), "power-automate-flow"),
    (("power apps", "powerapps", "canvas"), "power-apps-canvas"),
    (("vba", "macro", "excel", "office"), "excel-vba"),
]


def knowledge_for_category(text: str) -> str:
    """Resuelve el pack a partir del texto de la categoría/hint (sin `kind`).

    Matchea por palabra clave; si nada coincide, "" (sin ruido). Es lo que lleva
    el conocimiento a los modos que no importan un paquete estructurado."""
    low = (text or "").lower()
    for keywords, kind in _CATEGORY_KEYWORDS:
        if any(k in low for k in keywords):
            return knowledge_for(kind)
    return ""


# SALVAGUARDA: señales en el CONTENIDO real (estructura extraída, código, tema)
# para detectar la tecnología cuando ni el kind ni la categoría alcanzan. Son más
# específicas que las de categoría (huellas del material: tokens de un flujo JSON,
# de VBA, de Power Fx, de una entidad de Dataverse). Orden: lo más específico primero.
_CONTENT_SIGNALS: list[tuple[tuple[str, ...], str]] = [
    (("dataverse", "logicalname", "requiredlevel", "alternate key", "<entity",
      "<attribute", "rol de seguridad", "security role"), "dataverse-table"),
    (("power automate", "powerautomate", "openapiconnection", "runafter",
      "desencadenador"), "power-automate-flow"),
    (("power apps", "powerapps", "power fx", "patch(", "navigate(", ".pa.yaml"),
     "power-apps-canvas"),
    (("vba", "macro", "end sub", "dim ", "worksheet", "workbook"), "excel-vba"),
]


def knowledge_for_text(text: str) -> str:
    """Salvaguarda: detecta la tecnología LEYENDO el contenido y devuelve su pack.

    Último recurso cuando no hay `kind` fiable ni la categoría rutea. "" si no hay
    señales claras (no adivina)."""
    low = (text or "").lower()
    for signals, kind in _CONTENT_SIGNALS:
        if any(s in low for s in signals):
            return knowledge_for(kind)
    return ""


def known_kinds() -> list[str]:
    """Tipos con knowledge pack (para tests y para saber qué cubrimos)."""
    return sorted(_REGISTRY)
