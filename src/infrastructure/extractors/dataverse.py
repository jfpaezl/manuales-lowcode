"""Extractor de Dataverse (tablas/entidades + roles de seguridad).

ESPECULATIVO: se basa en el formato ESTÁNDAR del customizations.xml de una
Solution exportada de Power Platform. Como todavía no hay un export real para
testear, es DEFENSIVO: ante una estructura inesperada, agrega warnings y sigue
en vez de romper. Cuando llegue un export real, se ajustan los selectores.

No es un PackageExtractor por sí solo (no importás un customizations.xml suelto):
lo invoca el SolutionExtractor por composición, igual que flows y canvas apps.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from ...domain.entities import ExtractedPackage

# Mapa de RequiredLevel de Dataverse a un "¿requerido?" legible.
_REQUIRED = {
    "required": "Sí",
    "systemrequired": "Sí (sistema)",
    "recommended": "Recomendado",
    "none": "No",
}


class DataverseExtractor:
    def extract_from_customizations(
        self, xml_text: str
    ) -> tuple[list[ExtractedPackage], list[str]]:
        """Devuelve (componentes, warnings). Componentes: una tabla por entidad
        (kind «dataverse-table») y, si hay roles, uno de seguridad."""
        warnings: list[str] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            return [], [f"No pude parsear customizations.xml (Dataverse): {exc}"]

        components: list[ExtractedPackage] = []
        for ent in root.iter("Entity"):
            comp = self._table_component(ent, warnings)
            if comp is not None:
                components.append(comp)

        roles = list(root.iter("Role"))
        if roles:
            components.append(self._security_component(roles))

        return components, warnings

    # --- Tablas -----------------------------------------------------------

    def _table_component(
        self, ent: ET.Element, warnings: list[str]
    ) -> ExtractedPackage | None:
        name_el = ent.find("Name")
        logical = (name_el.text or "").strip() if name_el is not None else ""
        display = ""
        if name_el is not None:
            display = (name_el.get("LocalizedName") or "").strip()
        # Fallback: el atributo Name del <entity> interno.
        entity_el = ent.find(".//entity")
        if not logical and entity_el is not None:
            logical = (entity_el.get("Name") or "").strip()
        if not logical and not display:
            warnings.append("Encontré una entidad de Dataverse sin nombre; la salté.")
            return None
        display = display or logical

        lines = [f"# Tabla de Dataverse: {display}", ""]
        lines.append(f"Nombre lógico: {logical or '[COMPLETAR]'}")
        lines.append("")
        lines += self._attributes_table(ent, warnings)

        return ExtractedPackage(
            kind="dataverse-table",
            name=display,
            summary_markdown="\n".join(lines),
            unique_name=logical or display,  # el lógico es la identidad estable
        )

    def _attributes_table(self, ent: ET.Element, warnings: list[str]) -> list[str]:
        attrs = ent.findall(".//attributes/attribute")
        if not attrs:
            return ["(Sin columnas legibles en la estructura.)"]
        out = [
            "## Columnas",
            "",
            "| Nombre | Nombre lógico | Tipo | Requerido |",
            "| --- | --- | --- | --- |",
        ]
        for a in attrs:
            logical = self._text(a.find("LogicalName")) or a.get("PhysicalName", "")
            tipo = self._text(a.find("Type")) or "[COMPLETAR]"
            req_raw = (self._text(a.find("RequiredLevel")) or "none").lower()
            requerido = _REQUIRED.get(req_raw, req_raw)
            disp = a.find(".//displayname")
            display = (disp.get("description") if disp is not None else "") or logical
            out.append(f"| {display} | {logical} | {tipo} | {requerido} |")
        return out

    # --- Seguridad --------------------------------------------------------

    def _security_component(self, roles: list[ET.Element]) -> ExtractedPackage:
        lines = ["# Seguridad de Dataverse: roles", ""]
        lines.append("Roles de seguridad incluidos en la solución:")
        lines.append("")
        for r in roles:
            rn = r.find("RoleName")
            nombre = ""
            if rn is not None:
                nombre = (rn.get("LocalizedName") or rn.text or "").strip()
            lines.append(f"- {nombre or '[COMPLETAR]'}")
        lines.append("")
        lines.append(
            "Privilegios por tabla y niveles de acceso: [COMPLETAR] "
            "(no disponibles en la estructura extraída)."
        )
        return ExtractedPackage(
            kind="dataverse-security",
            name="Roles de seguridad",
            summary_markdown="\n".join(lines),
            unique_name="dataverse-security",
        )

    @staticmethod
    def _text(el: ET.Element | None) -> str:
        return (el.text or "").strip() if el is not None else ""
