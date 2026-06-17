"""Puertos: las interfaces que el dominio EXIGE al mundo exterior.

El dominio no sabe CÓMO se guarda en SQLite, CÓMO se genera el PDF ni
QUÉ modelo de IA responde. Solo declara el contrato. La infraestructura
implementa estos contratos (adaptadores). Eso es inversión de dependencias.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .change_tracking import StoredSnapshot
from .entities import Category, ExtractedPackage, Manual, ManualVersion


class UnsupportedPackageError(Exception):
    """El paquete no es reconocido por el extractor (formato/contenido inesperado)."""


class AIAuthError(Exception):
    """El proveedor de IA rechazó la autorización (HTTP 401): API key sin acceso al
    modelo, o modelo inexistente en esa conexión. Es SISTÉMICO (todas las llamadas
    a ese modelo van a fallar igual), así que no se trata como un fallo puntual."""


class ManualRepository(ABC):
    """Persistencia de manuales y sus versiones."""

    @abstractmethod
    def add(self, manual: Manual) -> Manual:
        """Crea un manual nuevo y devuelve el mismo con id asignado."""

    @abstractmethod
    def get(self, manual_id: int) -> Manual | None:
        """Trae un manual con todas sus versiones (sin los BLOB de PDF)."""

    @abstractmethod
    def list(self) -> list[Manual]:
        """Lista todos los manuales (metadatos, sin versiones pesadas)."""

    @abstractmethod
    def add_version(self, manual_id: int, version: ManualVersion) -> ManualVersion:
        """Agrega una versión nueva a un manual existente."""

    @abstractmethod
    def get_version(self, version_id: int) -> ManualVersion | None:
        """Trae una versión completa, incluido el PDF en BLOB."""

    @abstractmethod
    def rename(self, manual_id: int, new_title: str) -> None:
        """Cambia el título de un manual (no toca sus versiones/PDFs ya generados)."""

    @abstractmethod
    def delete(self, manual_id: int) -> None:
        """Borra un manual y sus versiones (cascade)."""

    @abstractmethod
    def reassign_category(self, old_label: str, new_label: str) -> None:
        """Reapunta todos los manuales de una categoría a otra (para renombrar)."""

    @abstractmethod
    def count_by_category(self, label: str) -> int:
        """Cuántos manuales usan esa categoría (para borrado seguro)."""


class PackageSnapshotRepository(ABC):
    """Persistencia de la «foto» de cada paquete importado (por unique_name).

    Es la memoria que habilita el seguimiento de cambios: guarda qué componentes
    y versión tenía la última importación, para comparar la próxima."""

    @abstractmethod
    def save(self, stored: StoredSnapshot) -> None:
        """Guarda/actualiza el snapshot (upsert por unique_name)."""

    @abstractmethod
    def get(self, unique_name: str) -> StoredSnapshot | None:
        """Trae el último snapshot de ese paquete, o None si nunca se importó."""


class CategoryRepository(ABC):
    """Persistencia del catálogo de categorías (editable por el usuario)."""

    @abstractmethod
    def list(self) -> list[Category]:
        """Todas las categorías, ordenadas por etiqueta."""

    @abstractmethod
    def add(self, category: Category) -> Category:
        """Agrega una categoría nueva. Falla si la etiqueta ya existe."""

    @abstractmethod
    def rename(self, old_label: str, new_label: str, ai_hint: str | None = None) -> None:
        """Renombra una categoría (y opcionalmente actualiza su ai_hint)."""

    @abstractmethod
    def delete(self, label: str) -> None:
        """Borra una categoría del catálogo."""

    @abstractmethod
    def get_hint(self, label: str) -> str:
        """Devuelve el ai_hint de una categoría (o la etiqueta si no existe)."""


class PDFRenderer(ABC):
    """Genera el PDF de una versión de manual."""

    @abstractmethod
    def render(self, manual: Manual, version: ManualVersion) -> bytes:
        """Devuelve el PDF como bytes (para guardar en SQLite)."""


class DocxRenderer(ABC):
    """Genera el documento Word (.docx) de una versión de manual.

    Hermano de PDFRenderer: misma entrada (manual + versión), otra salida. Permite
    descargar el manual en Word, editable, sin depender de Office ni de GTK."""

    @abstractmethod
    def render(self, manual: Manual, version: ManualVersion) -> bytes:
        """Devuelve el .docx como bytes (para escribir a disco)."""


class AIProvider(ABC):
    """Proveedor de IA. Cualquier endpoint OpenAI-compatible entra acá."""

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Manda system + user y devuelve el texto de la respuesta."""


class PackageExtractor(ABC):
    """Lee un paquete exportado (ZIP) y extrae su estructura/lógica.

    Un adaptador por familia de paquete (Power Automate, Power Apps, Solution).
    Si no reconoce el paquete, lanza UnsupportedPackageError.
    """

    @abstractmethod
    def supports(self, names: list[str]) -> bool:
        """¿Este extractor reconoce el paquete? Decide mirando los NOMBRES de
        archivo del ZIP (su contenido), no la extensión. Lo usa el dispatcher
        para enrutar cada ZIP al extractor correcto."""

    @abstractmethod
    def extract(self, data: bytes, filename: str = "") -> ExtractedPackage:
        """Recibe el ZIP en bytes y devuelve su contenido estructurado.

        filename es solo un hint (para el fallback de nombre); la decisión
        real se toma mirando el CONTENIDO del ZIP, no su extensión.
        """
