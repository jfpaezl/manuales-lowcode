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

CREATE TABLE IF NOT EXISTS package_snapshots (
    unique_name     TEXT    PRIMARY KEY,   -- identidad estable del paquete (Dataverse)
    version         TEXT    NOT NULL DEFAULT '',
    components_json TEXT    NOT NULL DEFAULT '[]',  -- [{name, kind, fingerprint}]
    manual_func_id  INTEGER REFERENCES manuals(id) ON DELETE SET NULL,
    manual_tec_id   INTEGER REFERENCES manuals(id) ON DELETE SET NULL,
    updated_at      TEXT    NOT NULL
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
# El ai_hint, además de describirle la tecnología a la IA, es lo que rutea al
# knowledge pack (knowledge_for_category matchea palabras clave del hint), así que
# debe contener el término de la tecnología (power apps / power automate / dataverse / vba).
_DEFAULT_CATEGORIES = [
    ("Solution", "una solución completa de Power Platform (Power Apps, Power Automate, "
                 "Dataverse e integraciones)"),
    ("Power Apps", "Power Apps (Power Platform): canvas apps"),
    ("Power Automate", "flujos de Power Automate (Power Platform)"),
    ("Dataverse", "tablas de Dataverse (Power Platform)"),
    ("Macros", "macros (Excel/VBA/Office)"),
    ("Python", "scripts de Python"),
    ("Low-Code", "una solución low-code"),
    ("Otro", "una automatización"),
]

# Categorías ligadas a un knowledge pack: GARANTIZAMOS que existan, también en DBs
# viejas (el seed normal solo corre con la tabla vacía). Sin estas, documentar un
# flujo o una tabla "desde un tema" no rutea al pack correcto.
_KNOWLEDGE_CATEGORIES = [
    ("Solution", "una solución completa de Power Platform (Power Apps, Power Automate, "
                 "Dataverse e integraciones)"),
    ("Power Apps", "Power Apps (Power Platform): canvas apps"),
    ("Power Automate", "flujos de Power Automate (Power Platform)"),
    ("Dataverse", "tablas de Dataverse (Power Platform)"),
    ("Macros", "macros (Excel/VBA/Office)"),
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
    _seed_knowledge_categories(conn)
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


def _seed_knowledge_categories(conn: sqlite3.Connection) -> None:
    """Garantiza que existan las categorías ligadas a un knowledge pack (sin pisar
    las que ya están). Corre siempre: si faltan —DB vieja o el usuario las borró—,
    se agregan, para que el ruteo categoría→pack funcione."""
    for label, hint in _KNOWLEDGE_CATEGORIES:
        conn.execute(
            "INSERT INTO categories (label, ai_hint) SELECT ?, ? "
            "WHERE NOT EXISTS (SELECT 1 FROM categories WHERE label = ?)",
            (label, hint, label),
        )
