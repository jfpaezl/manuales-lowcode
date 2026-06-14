"""Carga de configuración desde config.toml (tomllib, stdlib de Python 3.11+)."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .infrastructure.ai.openai_compatible_provider import AIConfig


@dataclass(frozen=True)
class AppConfig:
    db_path: str
    ai: AIConfig | None  # None si no configuraste IA todavía
    author: str = ""     # nombre del autor/responsable, recordado para el documento
    area: str = ""       # área/sector, recordada para los Datos generales
    worker_model: str = ""  # modelo "obrero" (chico) para la generación orquestada
    # Identidad de marca que aparece en la portada del PDF.
    brand_name: str = ""     # nombre de la empresa/marca
    brand_tagline: str = ""  # subtítulo/lema bajo la marca
    brand_logo: str = ""     # ruta a la imagen del logo (PNG/JPG)


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def save_config(
    path: str | Path = "config.toml",
    *,
    db_path: str,
    api_key: str,
    base_url: str,
    model: str,
    author: str = "",
    area: str = "",
    worker_model: str = "",
    brand_name: str = "",
    brand_tagline: str = "",
    brand_logo: str = "",
) -> None:
    """Escribe config.toml. tomllib solo lee, así que serializamos a mano
    (controlamos el formato, es seguro)."""
    content = (
        "# Generado por la app. Editable a mano si querés.\n\n"
        "[ai]\n"
        f'api_key  = "{_toml_escape(api_key)}"\n'
        f'base_url = "{_toml_escape(base_url)}"\n'
        f'model    = "{_toml_escape(model)}"\n'
        f'worker_model = "{_toml_escape(worker_model)}"\n\n'
        "[storage]\n"
        f'db_path = "{_toml_escape(db_path)}"\n\n'
        "[user]\n"
        f'name = "{_toml_escape(author)}"\n'
        f'area = "{_toml_escape(area)}"\n\n'
        "[brand]\n"
        f'name    = "{_toml_escape(brand_name)}"\n'
        f'tagline = "{_toml_escape(brand_tagline)}"\n'
        f'logo    = "{_toml_escape(brand_logo)}"\n'
    )
    Path(path).write_text(content, encoding="utf-8")


def load_config(path: str | Path = "config.toml") -> AppConfig:
    p = Path(path)
    if not p.exists():
        # Sin config: la app corre igual, pero sin IA y con db por defecto.
        return AppConfig(db_path="manuales.db", ai=None)

    data = tomllib.loads(p.read_text(encoding="utf-8"))

    storage = data.get("storage", {})
    db_path = storage.get("db_path", "manuales.db")
    user = data.get("user", {})
    author = user.get("name", "").strip()
    area = user.get("area", "").strip()

    brand = data.get("brand", {})
    brand_name = brand.get("name", "").strip()
    brand_tagline = brand.get("tagline", "").strip()
    brand_logo = brand.get("logo", "").strip()

    ai_data = data.get("ai", {})
    api_key = ai_data.get("api_key", "").strip()
    worker_model = ai_data.get("worker_model", "").strip()
    ai_cfg: AIConfig | None = None
    if api_key and api_key != "tu-api-key-aca":
        ai_cfg = AIConfig(
            api_key=api_key,
            base_url=ai_data.get("base_url", "https://opencode.ai/zen/go/v1"),
            model=ai_data.get("model", "glm-5.1"),
        )

    return AppConfig(
        db_path=db_path, ai=ai_cfg, author=author, area=area, worker_model=worker_model,
        brand_name=brand_name, brand_tagline=brand_tagline, brand_logo=brand_logo,
    )
