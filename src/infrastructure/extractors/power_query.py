"""Extractor de consultas Power Query (lenguaje M) de Excel.

Power Query NO es VBA y NO vive en vbaProject.bin. Vive en una parte customXml
del .xlsx/.xlsm, dentro de un elemento <DataMashup> cuyo texto es base64. Ese
base64 sigue el formato [MS-QDEFF]:

    [4 bytes versión][4 bytes largo del OPC][OPC = ZIP][...permisos/metadata...]

y el ZIP interno (OPC) trae `Formulas/Section1.m`, que es el código M con todas
las consultas (`shared <Nombre> = let ... in ...;`).

Lo parseamos con la STDLIB (base64 + struct + zipfile): no requiere Excel ni una
dependencia nueva. Es DEFENSIVO: ante cualquier cosa ilegible deja un warning y
sigue, no rompe la importación. Lo redacta la IA como cualquier otro componente.

No es un PackageExtractor suelto (no importás un customXml aislado): lo invoca el
ExcelWorkbookExtractor por composición, igual que Dataverse en una Solution.
"""
from __future__ import annotations

import base64
import re
import struct
import zipfile
from io import BytesIO

from ...domain.entities import ExtractedPackage

# El item customXml que contiene Power Query trae este elemento. El texto interno
# (entre las etiquetas) es el blob base64.
_DATAMASHUP = re.compile(
    r"<DataMashup\b[^>]*>(.*?)</DataMashup>", re.IGNORECASE | re.DOTALL
)
# Declaración de cada consulta dentro de Section1.m: `shared Nombre =` o
# `shared #"Nombre con espacios" =`. (Puede venir precedido de `[ ... ]` de
# anotaciones, que ignoramos para quedarnos con el nombre.)
_SHARED = re.compile(
    r'(?m)^\s*shared\s+(#"(?P<q>[^"]+)"|(?P<n>[A-Za-z_][\w\.]*))\s*=',
)


def _decode_xml(raw: bytes) -> str:
    """Decodifica una parte XML del paquete respetando su BOM.

    El item del DataMashup viene en UTF-16 (BOM \\xff\\xfe o \\xfe\\xff); el resto
    del paquete OOXML suele ser UTF-8. `decode('utf-16')` autodetecta el endianness
    a partir del BOM."""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    return raw.decode("utf-8-sig", errors="replace")


class PowerQueryExtractor:
    def read_component(self, data: bytes, filename: str = "") -> ExtractedPackage | None:
        """Devuelve el componente excel-powerquery, o None si el libro no tiene
        Power Query. Nunca lanza: ante un blob ilegible, devuelve el componente
        con un warning (así el manual igual avisa que había algo que no se leyó)."""
        try:
            zf = zipfile.ZipFile(BytesIO(data))
        except zipfile.BadZipFile:
            return None  # no es un OOXML; que otro extractor decida

        with zf:
            blob_b64 = self._find_mashup(zf)
            if blob_b64 is None:
                return None  # el libro no tiene Power Query

            name = self._name(filename)
            warnings: list[str] = []
            queries = self._parse(blob_b64, warnings)

        return ExtractedPackage(
            kind="excel-powerquery",
            name=name,
            summary_markdown=self._render(name, queries),
            warnings=warnings,
            unique_name=name,  # identidad para reconocer las mismas consultas al re-importar
        )

    # --- localización del blob --------------------------------------------

    @staticmethod
    def _find_mashup(zf: zipfile.ZipFile) -> str | None:
        """Busca el <DataMashup> en las partes customXml (customXml/itemN.xml o
        xl/customXml/itemN.xml). Devuelve el base64 interno o None.

        OJO: Excel guarda ESTE item en UTF-16 (con BOM), no en UTF-8 como el resto
        del paquete. Si lo decodificás como UTF-8, el XML queda con bytes nulos
        intercalados y el regex no matchea. Por eso detectamos el BOM. Y excluimos
        los itemProps (solo declaran el schemaRef, no traen el blob)."""
        candidates = [
            n for n in zf.namelist()
            if "customxml/item" in n.lower()
            and n.lower().endswith(".xml")
            and "itemprops" not in n.lower()
        ]
        for part in candidates:
            try:
                xml = _decode_xml(zf.read(part))
            except KeyError:
                continue
            m = _DATAMASHUP.search(xml)
            if m:
                return m.group(1).strip()
        return None

    # --- parseo del binario QDEFF -----------------------------------------

    def _parse(self, blob_b64: str, warnings: list[str]) -> list[tuple[str, str]]:
        """De base64 → OPC ZIP → Formulas/Section1.m → lista de (nombre, código M)."""
        try:
            raw = base64.b64decode(blob_b64, validate=False)
        except Exception:  # noqa: BLE001 — base64 inválido/corrupto
            warnings.append("No pude decodificar el blob de Power Query (base64 inválido).")
            return []

        section = self._read_section1(raw, warnings)
        if section is None:
            return []
        return self._split_queries(section)

    @staticmethod
    def _read_section1(raw: bytes, warnings: list[str]) -> str | None:
        """Salta la cabecera QDEFF, abre el OPC y lee Formulas/Section1.m."""
        if len(raw) < 8:
            warnings.append("El blob de Power Query está truncado.")
            return None
        try:
            opc_len = struct.unpack_from("<I", raw, 4)[0]  # bytes 0-3 = versión
            opc = raw[8:8 + opc_len]
            inner = zipfile.ZipFile(BytesIO(opc))
        except (zipfile.BadZipFile, struct.error):
            warnings.append("El paquete interno de Power Query no es un ZIP válido.")
            return None
        with inner:
            target = next(
                (n for n in inner.namelist() if n.lower().endswith("section1.m")),
                None,
            )
            if target is None:
                # Algún libro usa otro nombre de sección; agarramos cualquier .m.
                target = next((n for n in inner.namelist() if n.lower().endswith(".m")), None)
            if target is None:
                warnings.append("No encontré el código M (Formulas/Section1.m) en Power Query.")
                return None
            return inner.read(target).decode("utf-8", errors="replace")

    @staticmethod
    def _split_queries(section: str) -> list[tuple[str, str]]:
        """Parte Section1.m en (nombre, código) por cada `shared <Nombre> = ...;`.

        Si no matchea ninguna declaración (formato inesperado), devuelve el módulo
        entero como una sola «consulta» para no perder información."""
        matches = list(_SHARED.finditer(section))
        if not matches:
            cuerpo = section.strip()
            return [("Section1", cuerpo)] if cuerpo else []
        out: list[tuple[str, str]] = []
        for i, m in enumerate(matches):
            nombre = m.group("q") or m.group("n")
            fin = matches[i + 1].start() if i + 1 < len(matches) else len(section)
            codigo = section[m.start():fin].strip().rstrip(";").strip()
            out.append((nombre, codigo))
        return out

    # --- render -----------------------------------------------------------

    @staticmethod
    def _render(name: str, queries: list[tuple[str, str]]) -> str:
        lines = [
            f"# Consultas de Power Query: {name}", "",
            f"Contiene {len(queries)} consulta(s) de Power Query (lenguaje M).", "",
        ]
        for q_name, code in queries:
            lines.append(f"## Consulta: {q_name}")
            lines.append("```m")
            lines.append(code)
            lines.append("```")
            lines.append("")
        if not queries:
            lines.append("_(No se pudo leer el código M de las consultas.)_")
        return "\n".join(lines)

    @staticmethod
    def _name(filename: str) -> str:
        base = (filename or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        return base.rsplit(".", 1)[0] or "Power Query de Excel"
