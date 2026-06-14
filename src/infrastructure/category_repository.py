"""Implementación SQLite del puerto CategoryRepository."""
from __future__ import annotations

import sqlite3

from ..domain.entities import Category
from ..domain.ports import CategoryRepository


class SQLiteCategoryRepository(CategoryRepository):
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list(self) -> list[Category]:
        rows = self._conn.execute(
            "SELECT id, label, ai_hint FROM categories ORDER BY label COLLATE NOCASE"
        ).fetchall()
        return [Category(id=r["id"], label=r["label"], ai_hint=r["ai_hint"]) for r in rows]

    def add(self, category: Category) -> Category:
        try:
            cur = self._conn.execute(
                "INSERT INTO categories (label, ai_hint) VALUES (?, ?)",
                (category.label, category.ai_hint),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Ya existe una categoría '{category.label}'") from exc
        self._conn.commit()
        category.id = cur.lastrowid
        return category

    def rename(self, old_label: str, new_label: str, ai_hint: str | None = None) -> None:
        if ai_hint is None:
            self._conn.execute(
                "UPDATE categories SET label = ? WHERE label = ?", (new_label, old_label)
            )
        else:
            self._conn.execute(
                "UPDATE categories SET label = ?, ai_hint = ? WHERE label = ?",
                (new_label, ai_hint, old_label),
            )
        self._conn.commit()

    def delete(self, label: str) -> None:
        self._conn.execute("DELETE FROM categories WHERE label = ?", (label,))
        self._conn.commit()

    def get_hint(self, label: str) -> str:
        row = self._conn.execute(
            "SELECT ai_hint FROM categories WHERE label = ?", (label,)
        ).fetchone()
        # Si no existe o no tiene hint, usamos la etiqueta misma como descripción.
        return (row["ai_hint"] if row and row["ai_hint"] else label)
