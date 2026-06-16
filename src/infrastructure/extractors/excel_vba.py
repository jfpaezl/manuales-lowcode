"""Extractor de macros VBA de Excel (.xlsm).

El código VBA NO es texto plano: vive en xl/vbaProject.bin, un contenedor OLE2
con los módulos COMPRIMIDOS (formato [MS-OVBA] de Microsoft). Por eso usamos
oletools/olevba, que parsea el OLE2 y descomprime los módulos. No requiere
Excel instalado.

El resultado (summary_markdown con el código por módulo) lo redacta la IA, como
cualquier otro paquete importado.
"""
from __future__ import annotations

from ...domain.entities import ExtractedPackage
from ...domain.ports import PackageExtractor, UnsupportedPackageError


class ExcelVBAExtractor(PackageExtractor):
    def supports(self, names: list[str]) -> bool:
        # Un .xlsm con macros trae xl/vbaProject.bin dentro del ZIP.
        return any(n.lower().endswith("vbaproject.bin") for n in names)

    def extract(self, data: bytes, filename: str = "") -> ExtractedPackage:
        # Import perezoso: la app no obliga a tener oletools si no importás macros.
        from oletools.olevba import VBA_Parser

        try:
            vba = VBA_Parser(filename=filename or "macro.xlsm", data=data)
        except Exception as exc:  # noqa: BLE001 — archivo inválido/corrupto
            raise UnsupportedPackageError(
                f"No pude abrir el archivo de Excel: {exc}"
            ) from exc

        try:
            if not vba.detect_vba_macros():
                raise UnsupportedPackageError("El archivo no tiene macros VBA.")
            modules: list[tuple[str, str]] = []
            for (_f, _stream, vba_filename, vba_code) in vba.extract_macros():
                if vba_code and vba_code.strip():
                    modules.append((str(vba_filename), vba_code.strip()))
        finally:
            vba.close()

        if not modules:
            raise UnsupportedPackageError(
                "El archivo declara macros, pero los módulos no tienen código."
            )

        name = self._name(filename)
        lines = [
            f"# Macros VBA: {name}", "",
            f"Contiene {len(modules)} módulo(s) de código VBA.", "",
        ]
        for mod_name, code in modules:
            lines.append(f"## Módulo: {mod_name}")
            lines.append("```vba")
            lines.append(code)
            lines.append("```")
            lines.append("")

        return ExtractedPackage(
            kind="excel-vba", name=name, summary_markdown="\n".join(lines),
            unique_name=name,  # identidad para reconocer la misma macro al re-importar
        )

    @staticmethod
    def _name(filename: str) -> str:
        base = (filename or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        return base.rsplit(".", 1)[0] or "Macros de Excel"
