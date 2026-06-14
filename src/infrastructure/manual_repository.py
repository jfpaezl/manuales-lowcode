"""Implementación SQLite del puerto ManualRepository."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from ..domain.entities import Manual, ManualType, ManualVersion, Section
from ..domain.ports import ManualRepository


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _sections_to_json(sections: list[Section]) -> str:
    return json.dumps(
        [
            {
                "title": s.title,
                "content_html": s.content_html,
                "order": s.order,
                "source_markdown": s.source_markdown,
            }
            for s in sections
        ],
        ensure_ascii=False,
    )


def _sections_from_json(raw: str) -> list[Section]:
    # Tolerante a versiones viejas del JSON: solo tomamos claves conocidas.
    out: list[Section] = []
    for item in json.loads(raw or "[]"):
        out.append(
            Section(
                title=item.get("title", ""),
                content_html=item.get("content_html", ""),
                order=item.get("order", 0),
                source_markdown=item.get("source_markdown", ""),
            )
        )
    return out


class SQLiteManualRepository(ManualRepository):
    """Guarda manuales, versiones y PDFs (BLOB) en SQLite."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # --- Manuales ---------------------------------------------------------

    def add(self, manual: Manual) -> Manual:
        cur = self._conn.execute(
            """INSERT INTO manuals (title, type, category, description, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                manual.title,
                manual.type.value,
                manual.category,
                manual.description,
                _iso(manual.created_at),
                _iso(manual.updated_at),
            ),
        )
        self._conn.commit()
        manual.id = cur.lastrowid
        return manual

    def get(self, manual_id: int) -> Manual | None:
        row = self._conn.execute(
            "SELECT * FROM manuals WHERE id = ?", (manual_id,)
        ).fetchone()
        if row is None:
            return None
        manual = self._row_to_manual(row)
        # Versiones SIN el blob pesado (se pide aparte con get_version).
        vrows = self._conn.execute(
            """SELECT id, version, content_html, sections_json, change_note,
                      content_hash, created_at
               FROM manual_versions WHERE manual_id = ? ORDER BY version""",
            (manual_id,),
        ).fetchall()
        manual.versions = [self._row_to_version(v, with_blob=False) for v in vrows]
        return manual

    def list(self) -> list[Manual]:
        rows = self._conn.execute(
            "SELECT * FROM manuals ORDER BY updated_at DESC"
        ).fetchall()
        return [self._row_to_manual(r) for r in rows]

    def rename(self, manual_id: int, new_title: str) -> None:
        self._conn.execute(
            "UPDATE manuals SET title = ?, updated_at = ? WHERE id = ?",
            (new_title, _iso(datetime.now().astimezone()), manual_id),
        )
        self._conn.commit()

    def delete(self, manual_id: int) -> None:
        self._conn.execute("DELETE FROM manuals WHERE id = ?", (manual_id,))
        self._conn.commit()

    def reassign_category(self, old_label: str, new_label: str) -> None:
        self._conn.execute(
            "UPDATE manuals SET category = ? WHERE category = ?", (new_label, old_label)
        )
        self._conn.commit()

    def count_by_category(self, label: str) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM manuals WHERE category = ?", (label,)
        ).fetchone()[0]

    # --- Versiones --------------------------------------------------------

    def add_version(self, manual_id: int, version: ManualVersion) -> ManualVersion:
        cur = self._conn.execute(
            """INSERT INTO manual_versions
                 (manual_id, version, content_html, sections_json, pdf_blob,
                  change_note, content_hash, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                manual_id,
                version.version,
                version.content_html,
                _sections_to_json(version.sections),
                version.pdf_blob,
                version.change_note,
                version.content_hash,
                _iso(version.created_at),
            ),
        )
        self._conn.execute(
            "UPDATE manuals SET updated_at = ? WHERE id = ?",
            (_iso(version.created_at), manual_id),
        )
        self._conn.commit()
        version.id = cur.lastrowid
        return version

    def get_version(self, version_id: int) -> ManualVersion | None:
        row = self._conn.execute(
            "SELECT * FROM manual_versions WHERE id = ?", (version_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_version(row, with_blob=True)

    # --- Mapeos -----------------------------------------------------------

    @staticmethod
    def _row_to_manual(row: sqlite3.Row) -> Manual:
        return Manual(
            id=row["id"],
            title=row["title"],
            type=ManualType(row["type"]),
            category=row["category"],
            description=row["description"],
            created_at=_parse_dt(row["created_at"]),
            updated_at=_parse_dt(row["updated_at"]),
        )

    @staticmethod
    def _row_to_version(row: sqlite3.Row, *, with_blob: bool) -> ManualVersion:
        # content_hash NO se pasa: es una propiedad derivada de content_html.
        return ManualVersion(
            id=row["id"],
            version=row["version"],
            content_html=row["content_html"],
            sections=_sections_from_json(row["sections_json"]),
            pdf_blob=row["pdf_blob"] if with_blob else None,
            change_note=row["change_note"],
            created_at=_parse_dt(row["created_at"]),
        )
