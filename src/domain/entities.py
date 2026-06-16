"""Entidades del dominio.

Esta capa NO importa nada de PyQt, SQLite, WeasyPrint ni OpenAI.
Es Python puro. Si algún día cambiás todos esos detalles, este archivo
no se toca. Ese es el punto.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ManualType(str, Enum):
    """Tipo de manual."""
    FUNCIONAL = "funcional"
    TECNICO = "tecnico"


@dataclass
class Category:
    """Categoría de lo que se documenta. AHORA es un DATO, no un Enum.

    Se guarda en la tabla `categories` y la gestionás desde la app.
    `ai_hint` es la descripción que se le pasa a la IA en el prompt.
    """
    label: str
    ai_hint: str = ""
    id: int | None = None


@dataclass
class Section:
    """Una sección del manual.

    Guardamos el HTML (lo que va al PDF) Y el Markdown original
    (para poder re-editar sin perder el formato fuente).
    """
    title: str
    content_html: str
    order: int = 0
    source_markdown: str = ""


@dataclass
class ExtractedPackage:
    """Resultado de leer un paquete exportado (ej: un .zip de Power Automate).

    NO es el manual final: es la materia prima estructurada y FIEL que se
    extrae del paquete (trigger, acciones, orden, anidamientos). Después la
    IA la redacta como manual. Separar "extraer" de "redactar" es a propósito:
    lo extraído es verdad verificable; lo redactado es interpretación.
    """
    kind: str               # ej: "power-automate-flow"
    name: str               # nombre legible (displayName del flujo)
    summary_markdown: str   # estructura/lógica extraída, en Markdown
    warnings: list[str] = field(default_factory=list)  # lo que no se pudo leer
    # Subcomponentes (una Solution trae varios flujos/apps). Vacío = es atómico.
    # Permite repartir el trabajo entre "obreros" en la generación orquestada.
    components: list["ExtractedPackage"] = field(default_factory=list)
    # Versión del paquete (ej: "1.0.0.1" de una Solution). "" si no aplica/no se lee.
    version: str = ""
    # Identidad ESTABLE para reconocer el mismo paquete al re-importar (ej: el
    # UniqueName de Dataverse). Es la clave del seguimiento de cambios entre
    # versiones. Si el extractor no la setea, queda "".
    unique_name: str = ""

    @property
    def fingerprint(self) -> str:
        """Huella del contenido extraído. Misma estructura → misma huella; si el
        flujo/componente cambió, la huella cambia. Es lo que permite detectar un
        componente «modificado» entre dos importaciones."""
        return hashlib.sha256(self.summary_markdown.encode("utf-8")).hexdigest()

    @property
    def diff_units(self) -> list["ExtractedPackage"]:
        """Unidades comparables para el seguimiento de cambios.

        Una Solution se compara por sus componentes (flujos/apps). Un paquete
        atómico (flujo suelto, macro) no tiene sub-componentes: la unidad es el
        paquete entero (degrada con elegancia a «modificado / versión nueva»)."""
        return self.components if self.components else [self]


@dataclass
class ManualVersion:
    """Una versión congelada de un manual.

    Cada vez que guardás cambios se crea una versión nueva (inmutable),
    con su PDF generado y guardado como BLOB. Así tenés historial real.
    """
    version: int
    content_html: str
    sections: list[Section] = field(default_factory=list)
    pdf_blob: bytes | None = None
    change_note: str = ""
    created_at: datetime = field(default_factory=_now)
    id: int | None = None

    @property
    def content_hash(self) -> str:
        """Huella del contenido — sirve para evitar versiones duplicadas."""
        return hashlib.sha256(self.content_html.encode("utf-8")).hexdigest()


@dataclass
class Manual:
    """Un manual. Agrupa metadatos + su historial de versiones."""
    title: str
    type: ManualType
    category: str  # etiqueta de la categoría (referencia a categories.label)
    description: str = ""
    id: int | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    versions: list[ManualVersion] = field(default_factory=list)

    @property
    def latest_version(self) -> ManualVersion | None:
        return max(self.versions, key=lambda v: v.version, default=None)

    def next_version_number(self) -> int:
        latest = self.latest_version
        return (latest.version + 1) if latest else 1
