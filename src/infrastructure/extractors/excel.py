"""Extractor de libros de Excel: compone macros VBA + consultas Power Query.

Un .xlsx/.xlsm puede traer SOLO macros, SOLO Power Query, o LAS DOS. Son dos
tecnologías distintas que viven en lugares distintos del archivo (vbaProject.bin
vs el blob DataMashup de customXml), así que cada una tiene su propio extractor y
su propio `kind` ("kind manda": cada uno rutea su knowledge pack y su etiqueta de
obrero).

Este extractor NO reimplementa la lectura: DELEGA en ExcelVBAExtractor y
PowerQueryExtractor por composición (mismo patrón que SolutionExtractor con flows,
apps y Dataverse) y arma el paquete según lo que encuentre:

  - las dos        → paquete `excel-workbook` con un componente por tecnología
                     (dispara el orquestador/obrero en la generación).
  - una sola       → degrada al paquete atómico de esa tecnología (preserva el
                     comportamiento histórico: una macro suelta sigue siendo
                     `excel-vba` con el nombre del libro).
  - ninguna        → UnsupportedPackageError con mensaje claro.
"""
from __future__ import annotations

from ...domain.entities import ExtractedPackage
from ...domain.ports import PackageExtractor, UnsupportedPackageError
from .excel_vba import ExcelVBAExtractor
from .power_query import PowerQueryExtractor


class ExcelWorkbookExtractor(PackageExtractor):
    def __init__(
        self,
        vba_extractor: ExcelVBAExtractor | None = None,
        power_query_extractor: PowerQueryExtractor | None = None,
    ) -> None:
        self._vba = vba_extractor or ExcelVBAExtractor()
        self._pq = power_query_extractor or PowerQueryExtractor()

    def supports(self, names: list[str]) -> bool:
        # Macros → xl/vbaProject.bin. Power Query → una parte customXml (donde
        # vive el DataMashup). El contenido real lo confirma extract(); acá solo
        # decidimos si vale la pena intentar.
        low = [n.lower() for n in names]
        tiene_vba = any(n.endswith("vbaproject.bin") for n in low)
        tiene_customxml = any("customxml/item" in n and n.endswith(".xml") for n in low)
        return tiene_vba or tiene_customxml

    def extract(self, data: bytes, filename: str = "") -> ExtractedPackage:
        warnings: list[str] = []

        # VBA: si el archivo no se puede abrir, no matamos la importación: puede
        # que el Power Query sí sea legible. Degradamos a warning.
        try:
            vba = self._vba.read_component(data, filename)
        except UnsupportedPackageError as exc:
            warnings.append(f"No pude leer las macros VBA: {exc}")
            vba = None

        pq = self._pq.read_component(data, filename)  # nunca lanza

        components = [c for c in (vba, pq) if c is not None]

        if not components:
            raise UnsupportedPackageError(
                "El Excel no tiene macros VBA ni consultas de Power Query legibles."
            )

        if len(components) == 1:
            # Atómico: el paquete ES esa tecnología. Preserva nombre/identidad viejos.
            only = components[0]
            only.warnings.extend(warnings)
            return only

        # Los dos: libro multicomponente. El diff keya por NOMBRE de componente, así
        # que desambiguamos (si no, "ventas" vs "ventas" colisionaría).
        name = self._name(filename)
        vba.name = f"Macros VBA — {name}"
        pq.name = f"Power Query — {name}"

        lines = [
            f"# Libro de Excel: {name}", "",
            "Contiene macros VBA y consultas de Power Query.", "",
            "===== MACROS VBA =====", vba.summary_markdown, "",
            "===== POWER QUERY =====", pq.summary_markdown, "",
        ]
        warnings.extend(vba.warnings)
        warnings.extend(pq.warnings)

        return ExtractedPackage(
            kind="excel-workbook",
            name=name,
            summary_markdown="\n".join(lines),
            warnings=warnings,
            components=[vba, pq],  # VBA primero, Power Query después
            unique_name=name,      # identidad estable para el seguimiento de cambios
        )

    @staticmethod
    def _name(filename: str) -> str:
        base = (filename or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        return base.rsplit(".", 1)[0] or "Libro de Excel"
