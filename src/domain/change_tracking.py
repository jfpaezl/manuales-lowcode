"""Seguimiento de cambios entre dos importaciones del mismo paquete.

Lógica PURA de dominio: no sabe de SQLite, ni de IA, ni de PyQt. A partir de un
snapshot (la «foto» de la versión anterior) y el paquete recién extraído, decide
qué unidad se DEPRECÓ (estaba y ya no), cuál se MODIFICÓ (sigue pero cambió su
huella) y cuál es NUEVA. Eso es lo que después se marca en el manual y se anota
en el Versionamiento.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .entities import ExtractedPackage


class ChangeStatus(str, Enum):
    """Estado de una unidad comparable entre dos versiones."""
    UNCHANGED = "unchanged"
    MODIFIED = "modified"
    ADDED = "added"
    DEPRECATED = "deprecated"


@dataclass(frozen=True)
class ComponentSnapshot:
    """Foto mínima de una unidad: lo justo para comparar (no el contenido entero)."""
    name: str
    kind: str
    fingerprint: str


@dataclass(frozen=True)
class PackageSnapshot:
    """Foto de un paquete en una versión dada. Es lo que se persiste para poder
    comparar la PRÓXIMA importación contra esta."""
    unique_name: str
    version: str
    components: list[ComponentSnapshot] = field(default_factory=list)

    @classmethod
    def from_package(cls, pkg: ExtractedPackage) -> "PackageSnapshot":
        return cls(
            unique_name=pkg.unique_name,
            version=pkg.version,
            components=[
                ComponentSnapshot(name=u.name, kind=u.kind, fingerprint=u.fingerprint)
                for u in pkg.diff_units
            ],
        )


@dataclass(frozen=True)
class StoredSnapshot:
    """Un PackageSnapshot persistido + a qué manuales (funcional/técnico) pertenece.

    Las ids de manual son concesión a la persistencia: al re-importar, permiten
    saber a QUÉ manuales agregarles una versión nueva (no crear otros)."""
    snapshot: "PackageSnapshot"
    manual_func_id: int | None = None
    manual_tec_id: int | None = None


@dataclass(frozen=True)
class DiffResult:
    """Resultado de comparar la versión anterior con la nueva."""
    version_from: str
    version_to: str
    deprecated: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    is_first_import: bool = False

    @property
    def has_changes(self) -> bool:
        return bool(self.deprecated or self.modified or self.added)

    def status_of(self, name: str) -> ChangeStatus:
        """Estado de una unidad por nombre (para las marcas inline del render)."""
        if name in self.deprecated:
            return ChangeStatus.DEPRECATED
        if name in self.modified:
            return ChangeStatus.MODIFIED
        if name in self.added:
            return ChangeStatus.ADDED
        return ChangeStatus.UNCHANGED


def diff_package(old: PackageSnapshot | None, new_pkg: ExtractedPackage) -> DiffResult:
    """Compara el snapshot anterior con el paquete recién extraído.

    Si no hay snapshot previo (primera importación), no hay diff: todo es nuevo,
    pero no lo reportamos como «cambio» para no ensuciar el manual inicial."""
    new_snap = PackageSnapshot.from_package(new_pkg)
    if old is None:
        return DiffResult(
            version_from="", version_to=new_snap.version, is_first_import=True,
        )

    old_by_name = {c.name: c for c in old.components}
    new_by_name = {c.name: c for c in new_snap.components}

    deprecated, modified, added, unchanged = [], [], [], []
    for name, comp in new_by_name.items():
        if name not in old_by_name:
            added.append(name)
        elif comp.fingerprint != old_by_name[name].fingerprint:
            modified.append(name)
        else:
            unchanged.append(name)
    for name in old_by_name:
        if name not in new_by_name:
            deprecated.append(name)

    return DiffResult(
        version_from=old.version, version_to=new_snap.version,
        deprecated=deprecated, modified=modified, added=added, unchanged=unchanged,
    )
