"""Extractor de paquetes de Power Automate (export individual / legacy).

Lee el .zip que Power Automate genera al exportar un flujo como paquete
(fuera de una Solution) y reconstruye su estructura: trigger + acciones,
EN ORDEN DE EJECUCIÓN, respetando anidamientos (condiciones, bucles, etc.).

Estructura esperada del paquete:
    manifest.json
    Microsoft.Flow/flows/<guid>/definition.json   <- la lógica vive acá

El parser es DEFENSIVO a propósito: no clava la ruta exacta ni asume una
única forma del JSON. Busca el definition.json donde esté y tolera que el
workflow venga en properties.definition, en definition, o en la raíz.

El resultado (ExtractedPackage.summary_markdown) NO es el manual final:
es la materia prima estructurada y fiel que después redacta la IA.
"""
from __future__ import annotations

import json
import zipfile
from io import BytesIO
from typing import Any

from ...domain.entities import ExtractedPackage
from ...domain.ports import PackageExtractor, UnsupportedPackageError

# Traducción de tipos crudos del Workflow Definition Language a algo legible.
_TIPO_LEGIBLE = {
    "openapiconnection": "Conector",
    "openapiconnectionwebhook": "Conector (webhook)",
    "openapiconnectionnotification": "Conector (notificación)",
    "apiconnection": "Conector",
    "apiconnectionwebhook": "Conector (webhook)",
    "apiconnectionnotification": "Conector (notificación)",
    "if": "Condición",
    "foreach": "Para cada",
    "switch": "Conmutador",
    "scope": "Ámbito",
    "until": "Hacer hasta",
    "compose": "Redactar (Compose)",
    "http": "HTTP",
    "request": "Solicitud HTTP entrante",
    "response": "Respuesta",
    "recurrence": "Periódico (recurrence)",
    "initializevariable": "Inicializar variable",
    "setvariable": "Establecer variable",
    "incrementvariable": "Incrementar variable",
    "appendtoarrayvariable": "Agregar a variable de matriz",
    "table": "Crear tabla HTML/CSV",
    "select": "Seleccionar",
    "query": "Filtrar matriz",
    "join": "Unir",
    "parsejson": "Analizar JSON",
    "terminate": "Terminar",
    "wait": "Esperar (delay)",
}

# Tipos que contienen sub-acciones: hay que recursar dentro de ellos.
_CONTENEDORES = {"if", "foreach", "switch", "scope", "until"}


class PowerAutomateFlowExtractor(PackageExtractor):
    def supports(self, names: list[str]) -> bool:
        # Un export de flujo trae definition.json bajo Microsoft.Flow/.../flows/.
        return any(
            n.lower().endswith("definition.json") and "flow" in n.lower() for n in names
        )

    def extract(self, data: bytes, filename: str = "") -> ExtractedPackage:
        try:
            zf = zipfile.ZipFile(BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise UnsupportedPackageError("El archivo no es un ZIP válido.") from exc

        with zf:
            def_path = self._find_definition(zf.namelist())
            if def_path is None:
                raise UnsupportedPackageError(
                    "No encontré un definition.json de Power Automate en el ZIP. "
                    "¿Seguro que es un flujo exportado individualmente (no una Solution)?"
                )
            try:
                raw = json.loads(zf.read(def_path).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise UnsupportedPackageError(
                    f"El definition.json está corrupto o no es JSON válido: {exc}"
                ) from exc

        return self.build_from_raw(raw, filename)

    def build_from_raw(self, raw: Any, fallback_name: str = "") -> ExtractedPackage:
        """Describe un flujo desde su JSON ya parseado (sin abrir ZIP).

        Lo usa tanto extract() (flujo individual) como el SolutionExtractor,
        que lee los Workflows/*.json sueltos de adentro de una Solution."""
        workflow = self._locate_workflow(raw)
        if workflow is None:
            raise UnsupportedPackageError(
                "El JSON del flujo no tiene triggers/actions reconocibles."
            )

        name = self._display_name(raw, fallback_name)
        warnings: list[str] = []
        lines = [f"# Flujo de Power Automate: {name}", ""]

        triggers = self._as_dict(workflow.get("triggers"))
        lines.append("## Desencadenador (trigger)")
        if not triggers:
            lines.append("- (el flujo no declara trigger)")
            warnings.append("El flujo no declara trigger.")
        for tname, tbody in triggers.items():
            lines.extend(self._describe_step(tname, tbody, level=0))
        lines.append("")

        actions = self._as_dict(workflow.get("actions"))
        lines.append("## Acciones (en orden de ejecución)")
        if not actions:
            lines.append("- (sin acciones)")
        else:
            lines.extend(self._describe_actions(actions, level=0))

        return ExtractedPackage(
            kind="power-automate-flow",
            name=name,
            summary_markdown="\n".join(lines),
            warnings=warnings,
            unique_name=name,  # identidad para reconocer el mismo flujo al re-importar
        )

    # --- Localización defensiva ------------------------------------------

    @staticmethod
    def _find_definition(names: list[str]) -> str | None:
        candidatos = [n for n in names if n.lower().endswith("definition.json")]
        if not candidatos:
            return None
        # Preferí el que está bajo Microsoft.Flow/.../flows/ si hay varios.
        de_flow = [n for n in candidatos if "flow" in n.lower()]
        return (de_flow or candidatos)[0]

    @classmethod
    def _locate_workflow(cls, raw: Any) -> dict | None:
        if not isinstance(raw, dict):
            return None
        # El workflow puede venir anidado o directo en la raíz.
        for path in (("properties", "definition"), ("definition",)):
            node: Any = raw
            for key in path:
                node = node.get(key) if isinstance(node, dict) else None
            if isinstance(node, dict) and ("actions" in node or "triggers" in node):
                return node
        if "actions" in raw or "triggers" in raw:
            return raw
        return None

    @staticmethod
    def _display_name(raw: Any, filename: str) -> str:
        if isinstance(raw, dict):
            props = raw.get("properties")
            if isinstance(props, dict) and props.get("displayName"):
                return str(props["displayName"])
            if raw.get("name"):
                return str(raw["name"])
        base = (filename or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        return base.rsplit(".", 1)[0] or "Flujo sin nombre"

    # --- Recorrido del grafo ---------------------------------------------

    def _describe_actions(self, actions: dict, level: int) -> list[str]:
        out: list[str] = []
        for name in self._order_by_runafter(actions):
            out.extend(self._describe_step(name, actions[name], level))
        return out

    @staticmethod
    def _order_by_runafter(actions: dict) -> list[str]:
        """Orden topológico simple según runAfter. Ante ciclos o rarezas,
        agrega lo que quede en su orden natural (nunca pierde acciones)."""
        remaining = dict(actions)
        ordered: list[str] = []
        done: set[str] = set()
        while remaining:
            progreso = False
            for name, body in list(remaining.items()):
                deps = set((body or {}).get("runAfter") or {})
                # solo dependencias que existen en este nivel cuentan para el orden
                deps &= set(actions)
                if deps <= done:
                    ordered.append(name)
                    done.add(name)
                    del remaining[name]
                    progreso = True
            if not progreso:  # ciclo o dependencia externa: cortá y agregá el resto
                ordered.extend(remaining)
                break
        return ordered

    def _describe_step(self, name: str, body: Any, level: int) -> list[str]:
        body = body if isinstance(body, dict) else {}
        raw_type = str(body.get("type", "")).lower()
        legible = _TIPO_LEGIBLE.get(raw_type, body.get("type") or "Acción")
        indent = "  " * level
        nombre = name.replace("_", " ")
        detalle = self._summarize_inputs(raw_type, body)
        head = f"{indent}- **{nombre}** — {legible}"
        if detalle:
            head += f": {detalle}"
        out = [head]
        if raw_type in _CONTENEDORES:
            out.extend(self._describe_nested(body, raw_type, level + 1))
        return out

    def _describe_nested(self, body: dict, raw_type: str, level: int) -> list[str]:
        out: list[str] = []
        indent = "  " * level
        if raw_type == "switch":
            for cname, cbody in self._as_dict(body.get("cases")).items():
                out.append(f"{indent}- Caso «{cname}»:")
                out.extend(self._describe_actions(self._as_dict((cbody or {}).get("actions")), level + 1))
            default = self._as_dict((body.get("default") or {}).get("actions"))
            if default:
                out.append(f"{indent}- En caso contrario:")
                out.extend(self._describe_actions(default, level + 1))
            return out

        inner = self._as_dict(body.get("actions"))
        if inner:
            if raw_type == "if":
                out.append(f"{indent}- Si se cumple:")
            out.extend(self._describe_actions(inner, level + 1))
        if raw_type == "if":
            els = self._as_dict((body.get("else") or {}).get("actions"))
            if els:
                out.append(f"{indent}- Si no:")
                out.extend(self._describe_actions(els, level + 1))
        return out

    # --- Resumen de inputs (fiel, corto: la IA lo redacta lindo) ----------

    @classmethod
    def _summarize_inputs(cls, raw_type: str, body: dict) -> str:
        inputs = body.get("inputs")
        # Cualquier variante de conector: OpenApiConnection[Webhook|Notification], ApiConnection…
        if raw_type.startswith("openapiconnection") or raw_type.startswith("apiconnection"):
            host = inputs.get("host") if isinstance(inputs, dict) else None
            if isinstance(host, dict):
                # operationId + connectionName alcanzan; el apiId es una ruta larga y ruidosa.
                bits = [host.get("operationId"), host.get("connectionName")]
                return " / ".join(str(b) for b in bits if b)
            return ""
        if raw_type == "http" and isinstance(inputs, dict):
            return f"{inputs.get('method', '')} {inputs.get('uri', '')}".strip()
        if raw_type in ("initializevariable", "setvariable") and isinstance(inputs, dict):
            variables = inputs.get("variables")
            if isinstance(variables, list) and variables:
                v = variables[0]
                return str(v.get("name", "")) if isinstance(v, dict) else ""
            return str(inputs.get("name", ""))
        if raw_type == "compose":
            return cls._short(inputs)
        return ""

    @staticmethod
    def _short(value: Any, limit: int = 80) -> str:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        text = " ".join(text.split())
        return text if len(text) <= limit else text[: limit - 1] + "…"

    @staticmethod
    def _as_dict(value: Any) -> dict:
        return value if isinstance(value, dict) else {}
