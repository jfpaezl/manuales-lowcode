"""Extractor de canvas apps de Power Apps (.msapp).

El export de una canvas app es un ZIP de paquete que contiene un .msapp
anidado (otro ZIP). Dentro del .msapp, las versiones modernas del Studio
incluyen el CÓDIGO FUENTE en `Src/*.pa.yaml`: un árbol legible
`Screens -> control -> Children` con las fórmulas Power Fx. Eso parseamos.

Reconstruimos un "wireframe ESTRUCTURAL": la jerarquía real de contenedores
(con su dirección de layout), no posiciones por píxel. ¿Por qué? Porque las
apps con AutoLayout NO tienen X/Y fijas: la posición la calcula el runtime.
Dibujar cajas por coordenadas sería inventar. La jerarquía sí es la verdad.

El resultado NO es el manual final: es la materia prima fiel que redacta la IA.
"""
from __future__ import annotations

import json
import zipfile
from io import BytesIO
from typing import Any

import yaml

from ...domain.entities import ExtractedPackage
from ...domain.ports import PackageExtractor, UnsupportedPackageError


class _PowerFxYamlLoader(yaml.SafeLoader):
    """SafeLoader tolerante con el YAML que genera Power Apps.

    Power Apps escribe propiedades vacías como `Prop: =`. PyYAML interpreta el
    `=` suelto como el tag legacy 'value' (reliquia del spec viejo) y explota.
    Lo tratamos como un string común."""


_PowerFxYamlLoader.add_constructor(
    "tag:yaml.org,2002:value",
    lambda loader, node: loader.construct_scalar(node),
)

# Propiedades de COMPORTAMIENTO / CONTENIDO que importan para un manual.
# Las de estilo puro (Fill, Color, Font, Align, Border…) se descartan: son ruido.
_PROPS_INTERES = {
    "Text", "Items", "Default", "DefaultSelectedItems", "Value", "HintText",
    "Visible", "DisplayMode", "Update", "Items",
}


class PowerAppsCanvasExtractor(PackageExtractor):
    def supports(self, names: list[str]) -> bool:
        lower = [n.lower() for n in names]
        if any(n.endswith(".msapp") for n in lower):
            return True
        if any("microsoft.powerapps" in n for n in lower):
            return True
        # .msapp crudo (sin el envoltorio de paquete): tiene Header + Src/ o Controls/
        tiene_estructura = any(n.startswith(("src/", "controls/")) for n in lower)
        return tiene_estructura and "header.json" in lower

    def extract(self, data: bytes, filename: str = "") -> ExtractedPackage:
        msapp = self._open_msapp(data)
        with msapp:
            name = self._app_name(msapp, filename)
            warnings: list[str] = []
            lines = [f"# Aplicación Power Apps: {name}", ""]
            lines += self._data_sources_section(msapp, warnings)
            lines += self._screens_section(msapp, warnings)

        return ExtractedPackage(
            kind="power-apps-canvas", name=name,
            summary_markdown="\n".join(lines), warnings=warnings,
        )

    # --- Apertura del .msapp (anidado o crudo) ---------------------------

    def _open_msapp(self, data: bytes) -> zipfile.ZipFile:
        try:
            outer = zipfile.ZipFile(BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise UnsupportedPackageError("El archivo no es un ZIP válido.") from exc

        msapp_members = [n for n in outer.namelist() if n.lower().endswith(".msapp")]
        if msapp_members:
            inner_bytes = outer.read(msapp_members[0])
            outer.close()
            try:
                return zipfile.ZipFile(BytesIO(inner_bytes))
            except zipfile.BadZipFile as exc:
                raise UnsupportedPackageError("El .msapp interno está corrupto.") from exc

        # ¿El ZIP es el .msapp mismo? (export crudo)
        if any(n.lower().startswith(("src/", "controls/")) for n in outer.namelist()):
            return outer
        outer.close()
        raise UnsupportedPackageError(
            "No encontré un .msapp en el ZIP. ¿Seguro que es un export de Power Apps?"
        )

    # --- Secciones del markdown ------------------------------------------

    @staticmethod
    def _app_name(msapp: zipfile.ZipFile, filename: str) -> str:
        try:
            props = json.loads(msapp.read("Properties.json").decode("utf-8"))
            if props.get("Name"):
                return str(props["Name"])
        except (KeyError, json.JSONDecodeError, UnicodeDecodeError):
            pass
        base = (filename or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        return base.rsplit(".", 1)[0] or "App sin nombre"

    def _data_sources_section(self, msapp: zipfile.ZipFile, warnings: list[str]) -> list[str]:
        out = ["## Fuentes de datos"]
        try:
            raw = json.loads(msapp.read("References/DataSources.json").decode("utf-8"))
            entries = raw.get("DataSources", []) if isinstance(raw, dict) else raw
        except (KeyError, json.JSONDecodeError, UnicodeDecodeError):
            entries = []
        if not entries:
            out.append("- (no se declararon fuentes de datos)")
        for d in entries:
            if isinstance(d, dict) and d.get("Name"):
                tipo = d.get("Type")
                out.append(f"- {d['Name']}" + (f" ({tipo})" if tipo else ""))
        out.append("")
        return out

    def _screens_section(self, msapp: zipfile.ZipFile, warnings: list[str]) -> list[str]:
        out: list[str] = []
        screen_files = sorted(
            n for n in msapp.namelist()
            if n.lower().startswith("src/") and n.lower().endswith(".pa.yaml")
            and not n.lower().endswith("_editorstate.pa.yaml")
        )
        found_any = False
        for path in screen_files:
            try:
                doc = yaml.load(msapp.read(path).decode("utf-8"), Loader=_PowerFxYamlLoader) or {}
            except (yaml.YAMLError, UnicodeDecodeError):
                warnings.append(f"No pude parsear {path}.")
                continue
            screens = doc.get("Screens") if isinstance(doc, dict) else None
            if not isinstance(screens, dict):
                continue  # App.pa.yaml, componentes, etc.: se ignoran en v1
            for screen_name, body in screens.items():
                found_any = True
                out.extend(self._describe_screen(screen_name, body or {}))
        if not found_any:
            out.append("## Pantallas")
            out.append("- (no se encontraron pantallas en Src/*.pa.yaml)")
            warnings.append("No se encontraron pantallas legibles.")
        return out

    def _describe_screen(self, name: str, body: dict) -> list[str]:
        out = [f"## Pantalla: {name}"]
        for prop, formula in self._behavior_props(body.get("Properties")):
            out.append(f"- {prop}: {formula}")
        out.append("Estructura y controles:")
        for child in body.get("Children") or []:
            if isinstance(child, dict):
                for cname, cbody in child.items():
                    out.extend(self._describe_control(cname, cbody, level=0))
        out.append("")
        return out

    def _describe_control(self, name: str, body: Any, level: int) -> list[str]:
        body = body if isinstance(body, dict) else {}
        indent = "  " * level
        props = body.get("Properties") or {}

        comp = body.get("ComponentName")
        if comp:
            etiqueta = [f"componente: {comp}"]
        else:
            etiqueta = [self._tipo_control(body.get("Control"))]
        layout = self._layout_dir(props)
        if layout:
            etiqueta.append(layout)

        out = [f"{indent}- **{name}** [{' · '.join(etiqueta)}]"]
        for prop, formula in self._behavior_props(props):
            out.append(f"{indent}  · {prop}: {formula}")
        for child in body.get("Children") or []:
            if isinstance(child, dict):
                for cname, cbody in child.items():
                    out.extend(self._describe_control(cname, cbody, level + 1))
        return out

    # --- Helpers ---------------------------------------------------------

    @staticmethod
    def _tipo_control(control: Any) -> str:
        """'Button@2.2.0' -> 'Button'. La versión es ruido."""
        if not control:
            return "Control"
        return str(control).split("@", 1)[0]

    @staticmethod
    def _layout_dir(props: dict) -> str:
        raw = props.get("LayoutDirection") if isinstance(props, dict) else None
        if not raw:
            return ""
        low = str(raw).lower()
        if "horizontal" in low:
            return "horizontal"
        if "vertical" in low:
            return "vertical"
        return ""

    @classmethod
    def _behavior_props(cls, props: Any) -> list[tuple[str, str]]:
        if not isinstance(props, dict):
            return []
        out: list[tuple[str, str]] = []
        for prop, raw in props.items():
            if prop in _PROPS_INTERES or prop.startswith("On"):
                formula = cls._clean_formula(raw)
                if formula:
                    out.append((prop, formula))
        return out

    @staticmethod
    def _clean_formula(value: Any, limit: int = 120) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        if text.startswith("="):
            text = text[1:]
        text = " ".join(text.split())  # colapsa saltos de línea y espacios
        if not text:
            return ""
        return text if len(text) <= limit else text[: limit - 1] + "…"
