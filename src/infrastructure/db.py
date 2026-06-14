"""Conexión SQLite + esquema.

Una sola fuente de verdad para la estructura de la base.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS manuals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    type        TEXT    NOT NULL,   -- funcional | tecnico
    category    TEXT    NOT NULL,   -- etiqueta de categoría (ver tabla categories)
    description TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    label   TEXT    NOT NULL UNIQUE,
    ai_hint TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS manual_versions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    manual_id     INTEGER NOT NULL REFERENCES manuals(id) ON DELETE CASCADE,
    version       INTEGER NOT NULL,
    content_html  TEXT    NOT NULL,
    sections_json TEXT    NOT NULL DEFAULT '[]',
    pdf_blob      BLOB,
    change_note   TEXT    NOT NULL DEFAULT '',
    content_hash  TEXT    NOT NULL,
    created_at    TEXT    NOT NULL,
    UNIQUE (manual_id, version)
);

CREATE TABLE IF NOT EXISTS ai_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    manual_id  INTEGER REFERENCES manuals(id) ON DELETE SET NULL,
    mode       TEXT    NOT NULL,   -- generate | document_code | transcription | assist
    model      TEXT,
    prompt     TEXT,
    response   TEXT,
    created_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_versions_manual ON manual_versions(manual_id);
"""

# Categorías por defecto: (etiqueta, ai_hint para el prompt de la IA).
_DEFAULT_CATEGORIES = [
    ("Power Apps", "Power Apps (Power Platform)"),
    ("Macros", "macros (Excel/VBA/Office)"),
    ("Python", "scripts de Python"),
    ("Low-Code", "una solución low-code"),
    ("Otro", "una automatización"),
]

# Migración: viejos valores de Enum -> nuevas etiquetas (para datos preexistentes).
_LEGACY_CATEGORY_MAP = {
    "power_apps": "Power Apps",
    "macros": "Macros",
    "python": "Python",
    "low_code": "Low-Code",
    "other": "Otro",
}


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Abre la conexión, activa FKs y devuelve filas tipo dict."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Crea las tablas, siembra categorías por defecto y migra datos viejos."""
    conn.executescript(SCHEMA)
    _seed_categories(conn)
    _migrate_legacy_categories(conn)
    conn.commit()


def _seed_categories(conn: sqlite3.Connection) -> None:
    """Inserta las categorías por defecto solo si la tabla está vacía."""
    count = conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
    if count == 0:
        conn.executemany(
            "INSERT INTO categories (label, ai_hint) VALUES (?, ?)", _DEFAULT_CATEGORIES
        )


def _migrate_legacy_categories(conn: sqlite3.Connection) -> None:
    """Reapunta manuales con valores viejos de Enum a las nuevas etiquetas."""
    for old, new in _LEGACY_CATEGORY_MAP.items():
        conn.execute("UPDATE manuals SET category = ? WHERE category = ?", (new, old))
