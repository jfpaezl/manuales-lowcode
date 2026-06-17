"""Utilidades compartidas para leer DÓNDE viven los datos en Power Platform.

Tanto los flujos (los `parameters` de cada acción de conector) como las apps
(`References/DataSources.json`) referencian la MISMA información de ubicación:
sitio de SharePoint, archivo de Excel, tabla/lista. Antes esto se descartaba y
el manual lo dejaba en [COMPLETAR] aunque la ruta estuviera literal en el zip.

Es un util compartido (funciones puras), NO un extractor que depende de otro: lo
usan power_automate y power_apps por igual.
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Any

# connectionName / ApiId crudo (sin 'shared_' ni sufijo '-N') → nombre legible.
_CONECTOR_LEGIBLE = {
    "sharepointonline": "SharePoint",
    "excelonlinebusiness": "Excel Online",
    "excelonline": "Excel Online",
    "office365": "Outlook",
    "office365users": "Usuarios de Office 365",
    "teams": "Microsoft Teams",
    "sql": "SQL Server",
    "logicflows": "flujo de Power Automate",
    "onedriveforbusiness": "OneDrive para la Empresa",
    "dataverse": "Dataverse",
    "commondataservice": "Dataverse",
}


def connector_label(connection_name: Any) -> str:
    """'shared_sharepointonline-1' → 'SharePoint'. Conector desconocido → su
    nombre limpio (sin 'shared_' ni sufijo numérico)."""
    if not connection_name:
        return ""
    base = re.sub(r"^shared_", "", str(connection_name))
    base = re.sub(r"-\d+$", "", base).lower()
    return _CONECTOR_LEGIBLE.get(base, base)


def clean_path(value: Any, limit: int = 110) -> str:
    """Normaliza un valor de ruta para mostrarlo en el manual.

    A veces el sitio viene URL-encodeado (incluso DOBLE: 'https%253A%252F…'), así
    que lo des-encodeamos hasta estabilizar. Colapsa espacios y trunca lo muy largo."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if "%" in text:
        for _ in range(2):  # el doble-encode necesita dos pasadas
            nuevo = urllib.parse.unquote(text)
            if nuevo == text:
                break
            text = nuevo
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
