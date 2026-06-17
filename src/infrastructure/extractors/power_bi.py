"""Extractor de informes de Power BI (.pbit / .pbix).

Un .pbit (Plantilla) y un .pbix (informe) son ZIPs. Adentro, las dos piezas que
documentamos son:

  - DataModelSchema  → el MODELO tabular en JSON (tablas, columnas, MEDIDAS DAX,
                       columnas calculadas, relaciones y la consulta M de cada
                       tabla = su origen de datos). Es la joya.
  - Report/Layout    → el REPORTE: páginas y visuales (tipo + campos que usa).

OJO CRÍTICO con dos cosas, ambas verificadas contra un .pbit real:
  1. Esos JSON vienen en UTF-16 LE **sin BOM** (`{` + `\\x00`). Decodificarlos como
     UTF-8 los rompe. Detectamos el encoding por los bytes nulos intercalados.
  2. El .pbix NO trae DataModelSchema legible: el modelo va comprimido (XPress9,
     binario propietario). Por eso para documentar tablas/medidas hace falta el
     .pbit (Archivo → Exportar → Plantilla de Power BI). Si solo hay .pbix, igual
     documentamos el reporte y avisamos por warning.

Como un Excel con macros + Power Query, un Power BI con modelo + reporte se arma
como paquete multi-componente (cada parte con su `kind` y su knowledge pack). Si
solo hay una pieza legible, degrada al paquete atómico de esa pieza.
"""
from __future__ import annotations

import json
from io import BytesIO
import zipfile
from typing import Any

from ...domain.entities import ExtractedPackage
from ...domain.ports import PackageExtractor, UnsupportedPackageError

# Tablas que Power BI genera SOLO para las jerarquías de fecha automáticas. Son
# ruido (una por columna de fecha): no las documentamos ni a ellas ni a sus
# relaciones.
_AUTO_DATE_PREFIXES = ("DateTableTemplate_", "LocalDateTable_")

# visualType crudo → nombre legible para el manual.
_VISUAL_LEGIBLE = {
    "card": "Tarjeta", "cardVisual": "Tarjeta", "multiRowCard": "Tarjeta de varias filas",
    "tableEx": "Tabla", "pivotTable": "Matriz", "matrix": "Matriz",
    "slicer": "Segmentación (slicer)", "textbox": "Cuadro de texto",
    "image": "Imagen", "shape": "Forma", "actionButton": "Botón",
    "lineChart": "Gráfico de líneas", "columnChart": "Gráfico de columnas",
    "clusteredColumnChart": "Gráfico de columnas agrupadas",
    "clusteredBarChart": "Gráfico de barras agrupadas", "barChart": "Gráfico de barras",
    "lineClusteredColumnComboChart": "Gráfico combinado (columnas + líneas)",
    "lineStackedColumnComboChart": "Gráfico combinado (columnas apiladas + líneas)",
    "pieChart": "Gráfico circular", "donutChart": "Gráfico de anillos",
    "map": "Mapa", "filledMap": "Mapa coroplético", "gauge": "Medidor",
    "kpi": "KPI", "scatterChart": "Gráfico de dispersión", "treemap": "Treemap",
    "funnel": "Embudo", "waterfallChart": "Cascada",
}


def _decode(raw: bytes) -> str:
    """Decodifica una parte del .pbit/.pbix respetando su encoding.

    Power BI escribe estos JSON en UTF-16 LE SIN BOM. Sin esta detección, un
    decode UTF-8 explota o devuelve basura con bytes nulos."""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    if len(raw) >= 2 and raw[1] == 0 and raw[0] != 0:
        return raw.decode("utf-16-le")
    if len(raw) >= 2 and raw[0] == 0:
        return raw.decode("utf-16-be")
    return raw.decode("utf-8-sig", errors="replace")


def _expr(value: Any) -> str:
    """Las expresiones DAX/M vienen como lista de líneas (o string suelto)."""
    if isinstance(value, list):
        return "\n".join(str(x) for x in value).strip()
    return str(value or "").strip()


class PowerBIExtractor(PackageExtractor):
    def supports(self, names: list[str]) -> bool:
        low = [n.lower() for n in names]
        return any(n == "datamodelschema" or n.startswith("report/layout") for n in low)

    def extract(self, data: bytes, filename: str = "") -> ExtractedPackage:
        try:
            zf = zipfile.ZipFile(BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise UnsupportedPackageError("El archivo no es un ZIP válido.") from exc

        name = self._name(filename)
        warnings: list[str] = []
        with zf:
            names = zf.namelist()
            model = self._read_model(zf, names, name, warnings)
            report = self._read_report(zf, names, name, warnings)

        components = [c for c in (model, report) if c is not None]
        if not components:
            raise UnsupportedPackageError(
                "No encontré un modelo (DataModelSchema) ni un reporte (Report/Layout). "
                "¿Seguro que es un .pbit/.pbix de Power BI?"
            )

        if len(components) == 1:
            only = components[0]
            only.warnings.extend(warnings)
            return only

        # Modelo + reporte: informe multi-componente. El diff keya por nombre de
        # componente, así que los desambiguamos.
        model.name = f"Modelo de datos — {name}"
        report.name = f"Reporte — {name}"
        lines = [
            f"# Informe de Power BI: {name}", "",
            "Contiene el modelo de datos (tablas, medidas DAX, relaciones) y el "
            "reporte (páginas y visuales).", "",
            "===== MODELO DE DATOS =====", model.summary_markdown, "",
            "===== REPORTE =====", report.summary_markdown, "",
        ]
        warnings.extend(model.warnings)
        warnings.extend(report.warnings)
        return ExtractedPackage(
            kind="power-bi", name=name, summary_markdown="\n".join(lines),
            warnings=warnings, components=[model, report], unique_name=name,
        )

    # --- Modelo de datos --------------------------------------------------

    def _read_model(
        self, zf: zipfile.ZipFile, names: list[str], name: str, warnings: list[str]
    ) -> ExtractedPackage | None:
        path = next((n for n in names if n.lower() == "datamodelschema"), None)
        if path is None:
            # .pbix: el modelo está comprimido (XPress9), no es legible en Python.
            if any(n.lower() == "datamodel" for n in names):
                warnings.append(
                    "El modelo de datos viene comprimido (.pbix): no puedo leer "
                    "tablas/medidas/DAX. Exportá el informe como Plantilla (.pbit) "
                    "para documentarlo: Archivo → Exportar → Plantilla de Power BI."
                )
            return None
        try:
            doc = json.loads(_decode(zf.read(path)))
        except (json.JSONDecodeError, KeyError) as exc:
            warnings.append(f"No pude leer el modelo de datos: {exc}")
            return None

        model = doc.get("model") if isinstance(doc, dict) else None
        if not isinstance(model, dict):
            warnings.append("El DataModelSchema no tiene un nodo 'model' reconocible.")
            return None

        tables = [
            t for t in (model.get("tables") or [])
            if isinstance(t, dict) and not self._is_auto_date(t.get("name", ""))
        ]
        rels = [
            r for r in (model.get("relationships") or [])
            if isinstance(r, dict)
            and not self._is_auto_date(r.get("fromTable", ""))
            and not self._is_auto_date(r.get("toTable", ""))
        ]
        n_med = sum(len(t.get("measures") or []) for t in tables)

        lines = [
            f"# Modelo de datos de Power BI: {name}", "",
            f"Contiene {len(tables)} tabla(s), {n_med} medida(s) y "
            f"{len(rels)} relación(es).", "",
        ]
        for t in tables:
            lines.extend(self._describe_table(t))
        lines.extend(self._describe_relationships(rels))

        return ExtractedPackage(
            kind="power-bi-model", name=name, summary_markdown="\n".join(lines),
            unique_name=name,
        )

    def _describe_table(self, t: dict) -> list[str]:
        out = [f"## Tabla: {t.get('name', '(sin nombre)')}"]

        m_expr = self._partition_m(t)
        if m_expr:
            out.append("Origen (consulta Power Query / M):")
            out.append("```m")
            out.append(m_expr)
            out.append("```")

        cols = [c for c in (t.get("columns") or []) if isinstance(c, dict)]
        if cols:
            out.append("Columnas:")
            for c in cols:
                out.extend(self._describe_column(c))

        meds = [m for m in (t.get("measures") or []) if isinstance(m, dict)]
        if meds:
            out.append("Medidas:")
            for m in meds:
                out.extend(self._describe_measure(m))
        out.append("")
        return out

    @staticmethod
    def _partition_m(t: dict) -> str:
        for p in t.get("partitions") or []:
            src = p.get("source") if isinstance(p, dict) else None
            if isinstance(src, dict) and str(src.get("type", "")).lower() == "m":
                return _expr(src.get("expression"))
        return ""

    @staticmethod
    def _describe_column(c: dict) -> list[str]:
        nombre = c.get("name", "(sin nombre)")
        tipo = c.get("dataType", "")
        marcas = []
        if c.get("isHidden"):
            marcas.append("oculta")
        es_calc = str(c.get("type", "")).lower() == "calculated"
        if es_calc:
            marcas.append("calculada")
        suf = f" ({tipo}{', ' + ', '.join(marcas) if marcas else ''})" if tipo or marcas else ""
        if es_calc and _expr(c.get("expression")):
            return [f"- {nombre}{suf}:", "```dax", _expr(c.get("expression")), "```"]
        return [f"- {nombre}{suf}"]

    @staticmethod
    def _describe_measure(m: dict) -> list[str]:
        nombre = m.get("name", "(sin nombre)")
        extras = []
        if m.get("formatString"):
            extras.append(f"formato: {m['formatString']}")
        if m.get("displayFolder"):
            extras.append(f"carpeta: {m['displayFolder']}")
        cab = f"- **{nombre}**" + (f" [{' · '.join(extras)}]" if extras else "") + ":"
        out = [cab, "```dax", _expr(m.get("expression")), "```"]
        if m.get("description"):
            out.insert(1, f"  {m['description']}")
        return out

    def _describe_relationships(self, rels: list[dict]) -> list[str]:
        if not rels:
            return []
        out = ["## Relaciones"]
        for r in rels:
            estado = "activa" if r.get("isActive") in (None, True) else "inactiva"
            cross = r.get("crossFilteringBehavior")
            extra = f", filtro {cross}" if cross else ""
            out.append(
                f"- {r.get('fromTable')}[{r.get('fromColumn')}] → "
                f"{r.get('toTable')}[{r.get('toColumn')}] ({estado}{extra})"
            )
        out.append("")
        return out

    @staticmethod
    def _is_auto_date(table_name: str) -> bool:
        return str(table_name).startswith(_AUTO_DATE_PREFIXES)

    # --- Reporte ----------------------------------------------------------

    def _read_report(
        self, zf: zipfile.ZipFile, names: list[str], name: str, warnings: list[str]
    ) -> ExtractedPackage | None:
        path = next((n for n in names if n.lower().startswith("report/layout")), None)
        if path is None:
            return None
        try:
            layout = json.loads(_decode(zf.read(path)))
        except (json.JSONDecodeError, KeyError) as exc:
            warnings.append(f"No pude leer el reporte: {exc}")
            return None

        sections = layout.get("sections") if isinstance(layout, dict) else None
        if not isinstance(sections, list):
            warnings.append("El reporte no tiene páginas (sections) reconocibles.")
            return None

        lines = [
            f"# Reporte de Power BI: {name}", "",
            f"Contiene {len(sections)} página(s).", "",
        ]
        for s in sections:
            lines.extend(self._describe_page(s if isinstance(s, dict) else {}))

        return ExtractedPackage(
            kind="power-bi-report", name=name, summary_markdown="\n".join(lines),
            unique_name=name,
        )

    def _describe_page(self, s: dict) -> list[str]:
        nombre = s.get("displayName") or s.get("name") or "(sin nombre)"
        visuals = [v for v in (s.get("visualContainers") or []) if isinstance(v, dict)]
        out = [f"## Página: {nombre}", f"{len(visuals)} visual(es)."]
        for vc in visuals:
            out.extend(self._describe_visual(vc))
        out.append("")
        return out

    def _describe_visual(self, vc: dict) -> list[str]:
        try:
            cfg = json.loads(vc.get("config") or "{}")
        except json.JSONDecodeError:
            return []
        sv = cfg.get("singleVisual") if isinstance(cfg, dict) else None
        if not isinstance(sv, dict):
            return []
        tipo_raw = sv.get("visualType", "")
        tipo = _VISUAL_LEGIBLE.get(tipo_raw, tipo_raw or "visual")
        campos = self._visual_fields(sv)
        if campos:
            return [f"- {tipo}: " + " · ".join(campos)]
        return [f"- {tipo}"]

    @staticmethod
    def _visual_fields(sv: dict) -> list[str]:
        out: list[str] = []
        projections = sv.get("projections")
        if isinstance(projections, dict):
            for role, items in projections.items():
                for it in items or []:
                    if isinstance(it, dict) and it.get("queryRef"):
                        out.append(f"{role}: {it['queryRef']}")
        return out

    # --- Helpers ----------------------------------------------------------

    @staticmethod
    def _name(filename: str) -> str:
        base = (filename or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        return base.rsplit(".", 1)[0] or "Informe de Power BI"
