"""Implementación SQLite del puerto PackageSnapshotRepository.

Guarda UNA fila por paquete (clave: unique_name). Upsert: cada importación
pisa la foto anterior, porque para el diff solo importa comparar contra la
ÚLTIMA versión importada."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from ..domain.change_tracking import ComponentSnapshot, PackageSnapshot, StoredSnapshot
from ..domain.ports import PackageSnapshotRepository


class SQLitePackageSnapshotRepository(PackageSnapshotRepository):
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save(self, stored: StoredSnapshot) -> None:
        snap = stored.snapshot
        if not snap.unique_name:
            return  # sin identidad no hay nada que rastrear
        components_json = json.dumps(
            [
                {"name": c.name, "kind": c.kind, "fingerprint": c.fingerprint}
                for c in snap.components
            ],
            ensure_ascii=False,
        )
        self._conn.execute(
            """INSERT INTO package_snapshots
                 (unique_name, version, components_json, manual_func_id,
                  manual_tec_id, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(unique_name) DO UPDATE SET
                 version         = excluded.version,
                 components_json = excluded.components_json,
                 manual_func_id  = excluded.manual_func_id,
                 manual_tec_id   = excluded.manual_tec_id,
                 updated_at      = excluded.updated_at""",
            (
                snap.unique_name,
                snap.version,
                components_json,
                stored.manual_func_id,
                stored.manual_tec_id,
                datetime.now().astimezone().isoformat(),
            ),
        )
        self._conn.commit()

    def get(self, unique_name: str) -> StoredSnapshot | None:
        if not unique_name:
            return None
        row = self._conn.execute(
            "SELECT * FROM package_snapshots WHERE unique_name = ?", (unique_name,)
        ).fetchone()
        if row is None:
            return None
        components = [
            ComponentSnapshot(name=c["name"], kind=c["kind"], fingerprint=c["fingerprint"])
            for c in json.loads(row["components_json"] or "[]")
        ]
        return StoredSnapshot(
            snapshot=PackageSnapshot(
                unique_name=row["unique_name"],
                version=row["version"],
                components=components,
            ),
            manual_func_id=row["manual_func_id"],
            manual_tec_id=row["manual_tec_id"],
        )
