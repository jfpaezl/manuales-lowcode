"""Extractor de Soluciones de Power Platform (.zip de Dataverse, managed o no).

Una Solution es el contenedor de alto nivel. Adentro trae:
  - Workflows/*.json   → flujos de Power Automate (JSON suelto, la lógica vive
                         en properties.definition, igual que el export individual)
  - CanvasApps/*.msapp → canvas apps de Power Apps
  - solution.xml       → metadata (nombre, versión)

Este extractor NO reimplementa nada: recorre la solución y DELEGA cada componente
al extractor que ya existe (PowerAutomate / PowerApps), vía composición. Reutilizar
en vez de duplicar: por eso separamos build_from_raw en el extractor de flujos.
"""
from __future__ import annotations

import json
import re
import zipfile
from io import BytesIO

from ...domain.entities import ExtractedPackage
from ...domain.ports import PackageExtractor, UnsupportedPackageError
from .dataverse import DataverseExtractor
from .power_apps import PowerAppsCanvasExtractor
from .power_automate import PowerAutomateFlowExtractor

# Sufijo GUID que Dataverse agrega al nombre de archivo (…-XXXXXXXX-....json).
_GUID_SUFFIX = re.compile(
    r"-[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"
)


class SolutionExtractor(PackageExtractor):
    def __init__(
        self,
        flow_extractor: PowerAutomateFlowExtractor | None = None,
        canvas_extractor: PowerAppsCanvasExtractor | None = None,
        dataverse_extractor: DataverseExtractor | None = None,
    ) -> None:
        self._flows = flow_extractor or PowerAutomateFlowExtractor()
        self._canvas = canvas_extractor or PowerAppsCanvasExtractor()
        self._dataverse = dataverse_extractor or DataverseExtractor()

    def supports(self, names: list[str]) -> bool:
        return any(n.lower().endswith("solution.xml") for n in names)

    def extract(self, data: bytes, filename: str = "") -> ExtractedPackage:
        try:
            zf = zipfile.ZipFile(BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise UnsupportedPackageError("El archivo no es un ZIP válido.") from exc

        with zf:
            names = zf.namelist()
            if not any(n.lower().endswith("solution.xml") for n in names):
                raise UnsupportedPackageError(
                    "No encontré solution.xml. ¿Seguro que es una Solution exportada?"
                )
            sol_name, version, unique_name = self._solution_meta(zf, names, filename)
            warnings: list[str] = []
            flows = self._extract_flows(zf, names, warnings)
            apps = self._extract_apps(zf, names, warnings)
            dataverse = self._extract_dataverse(zf, names, warnings)

        tables = [c for c in dataverse if c.kind == "dataverse-table"]
        lines = [f"# Solución de Power Platform: {sol_name}"]
        if version:
            lines.append(f"Versión: {version}")
        lines.append("")
        lines.append(
            f"Contiene {len(flows)} flujo(s) de Power Automate, "
            f"{len(apps)} app(s) de Power Apps y {len(tables)} tabla(s) de Dataverse."
        )
        lines.append("")

        for i, pkg in enumerate(flows, 1):
            lines.append(f"===== FLUJO {i} de {len(flows)} =====")
            lines.append(pkg.summary_markdown)
            lines.append("")
            warnings.extend(pkg.warnings)
        for i, pkg in enumerate(apps, 1):
            lines.append(f"===== APP DE POWER APPS {i} de {len(apps)} =====")
            lines.append(pkg.summary_markdown)
            lines.append("")
            warnings.extend(pkg.warnings)
        for pkg in dataverse:
            lines.append(f"===== DATAVERSE: {pkg.name} =====")
            lines.append(pkg.summary_markdown)
            lines.append("")

        if not flows and not apps and not dataverse:
            warnings.append("La solución no tenía flujos, canvas apps ni tablas legibles.")

        return ExtractedPackage(
            kind="power-platform-solution",
            name=sol_name,
            summary_markdown="\n".join(lines),
            warnings=warnings,
            # Orden de componentes: tablas primero (la data es la base), luego
            # flujos/apps que la usan, y la seguridad. Para los obreros y el diff.
            components=dataverse + flows + apps,
            version=version,
            unique_name=unique_name,  # identidad estable para el seguimiento de cambios
        )

    # --- helpers ---------------------------------------------------------

    @staticmethod
    def _solution_meta(
        zf: zipfile.ZipFile, names: list[str], filename: str
    ) -> tuple[str, str, str]:
        """Devuelve (nombre legible, versión, unique_name).

        El unique_name es la identidad ESTABLE de Dataverse: no cambia entre
        versiones de la misma Solution, así que es la clave para reconocer un
        re-import y poder comparar contra la versión anterior."""
        path = next((n for n in names if n.lower().endswith("solution.xml")), None)
        sol_name = version = unique_name = ""
        if path is not None:
            try:
                xml = zf.read(path).decode("utf-8", errors="replace")
            except KeyError:
                xml = ""
            m = re.search(r"<UniqueName[^>]*>([^<]+)</UniqueName>", xml)
            if m:
                unique_name = m.group(1).strip()
            m = re.search(r'<LocalizedName\s+description="([^"]+)"', xml)
            if m:
                sol_name = m.group(1)
            if not sol_name:
                sol_name = unique_name
            m = re.search(r"<Version[^>]*>([^<]+)</Version>", xml)
            if m:
                version = m.group(1).strip()
        if not sol_name:
            base = (filename or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
            sol_name = base.rsplit(".", 1)[0] or "Solución sin nombre"
        return sol_name, version, unique_name

    def _extract_flows(
        self, zf: zipfile.ZipFile, names: list[str], warnings: list[str]
    ) -> list[ExtractedPackage]:
        out: list[ExtractedPackage] = []
        paths = sorted(
            n for n in names
            if n.lower().startswith("workflows/") and n.lower().endswith(".json")
        )
        for p in paths:
            try:
                raw = json.loads(zf.read(p).decode("utf-8"))
                out.append(self._flows.build_from_raw(raw, self._clean_name(p)))
            except (json.JSONDecodeError, UnicodeDecodeError, UnsupportedPackageError) as exc:
                warnings.append(f"No pude leer el flujo {p.rsplit('/', 1)[-1]}: {exc}")
        return out

    def _extract_apps(
        self, zf: zipfile.ZipFile, names: list[str], warnings: list[str]
    ) -> list[ExtractedPackage]:
        out: list[ExtractedPackage] = []
        paths = sorted(
            n for n in names
            if n.lower().startswith("canvasapps/") and n.lower().endswith(".msapp")
        )
        for p in paths:
            try:
                out.append(self._canvas.extract(zf.read(p), self._clean_name(p)))
            except UnsupportedPackageError as exc:
                warnings.append(f"No pude leer la app {p.rsplit('/', 1)[-1]}: {exc}")
        return out

    def _extract_dataverse(
        self, zf: zipfile.ZipFile, names: list[str], warnings: list[str]
    ) -> list[ExtractedPackage]:
        """Tablas y roles de Dataverse desde customizations.xml (si lo hay)."""
        path = next((n for n in names if n.lower().endswith("customizations.xml")), None)
        if path is None:
            return []
        try:
            xml = zf.read(path).decode("utf-8", errors="replace")
        except KeyError:
            return []
        comps, w = self._dataverse.extract_from_customizations(xml)
        warnings.extend(w)
        return comps

    @staticmethod
    def _clean_name(path: str) -> str:
        stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        return _GUID_SUFFIX.sub("", stem)
