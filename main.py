"""Composition root: acá se cablea TODO.

Este es el ÚNICO lugar que conoce las implementaciones concretas
(SQLite, WeasyPrint, OpenCode). El resto de la app trabaja con interfaces.
Querés cambiar de motor de PDF o de IA? Se cambia acá, en una línea.
"""
from __future__ import annotations

import sys

from src.application.manual_service import ManualService
from src.config import load_config, save_config
from src.infrastructure.ai.openai_compatible_provider import (
    AIConfig,
    OpenAICompatibleProvider,
    list_available_models,
)
from src.infrastructure.category_repository import SQLiteCategoryRepository
from src.infrastructure.db import connect, init_db
from src.infrastructure.docx.python_docx_renderer import PythonDocxRenderer
from src.infrastructure.extractors.dispatcher import CompositePackageExtractor
from src.infrastructure.extractors.excel import ExcelWorkbookExtractor
from src.infrastructure.extractors.power_apps import PowerAppsCanvasExtractor
from src.infrastructure.extractors.power_automate import PowerAutomateFlowExtractor
from src.infrastructure.extractors.power_bi import PowerBIExtractor
from src.infrastructure.extractors.solution import SolutionExtractor
from src.infrastructure.manual_repository import SQLiteManualRepository
from src.infrastructure.package_snapshot_repository import SQLitePackageSnapshotRepository
from src.infrastructure.pdf.weasyprint_renderer import WeasyPrintRenderer

CONFIG_PATH = "config.toml"


def _worker_provider(api_key: str, base_url: str, worker_model: str, timeout: float = 300.0):
    """Crea el proveedor 'obrero' (modelo chico). Mismo endpoint/clave que el
    orquestador, distinto modelo. Si no hay worker_model, no hay obrero."""
    if not (api_key and worker_model):
        return None
    return OpenAICompatibleProvider(
        AIConfig(api_key=api_key, base_url=base_url, model=worker_model, timeout=timeout)
    )


def _build_worker(config):
    if not config.ai:
        return None
    return _worker_provider(
        config.ai.api_key, config.ai.base_url, config.worker_model, config.ai.timeout
    )


def main() -> int:
    from PyQt6.QtWidgets import QApplication

    config = load_config(CONFIG_PATH)

    # --- Infraestructura (los detalles enchufables) ---
    conn = connect(config.db_path)
    init_db(conn)
    repo = SQLiteManualRepository(conn)
    categories = SQLiteCategoryRepository(conn)
    snapshots = SQLitePackageSnapshotRepository(conn)
    renderer = WeasyPrintRenderer(
        brand=config.brand_name, tagline=config.brand_tagline, logo_path=config.brand_logo
    )
    docx_renderer = PythonDocxRenderer(
        brand=config.brand_name, tagline=config.brand_tagline, logo_path=config.brand_logo
    )
    ai = OpenAICompatibleProvider(config.ai) if config.ai else None
    worker_ai = _build_worker(config)
    # OJO el orden: la Solution va PRIMERO porque también contiene .msapp adentro
    # (si no, el extractor de Power Apps la agarraría por error).
    extractor = CompositePackageExtractor([
        SolutionExtractor(),
        PowerAutomateFlowExtractor(),
        PowerAppsCanvasExtractor(),
        PowerBIExtractor(),  # informe .pbit/.pbix: modelo de datos + reporte
        ExcelWorkbookExtractor(),  # macros VBA + consultas Power Query
    ])

    # --- Servicio (el caso de uso) ---
    service = ManualService(
        repo, renderer=renderer, ai=ai, categories=categories, extractor=extractor,
        worker_ai=worker_ai, snapshots=snapshots, docx_renderer=docx_renderer,
    )

    # --- Estado de config en memoria (para no pisar campos al guardar) ---
    state = {
        "api_key": config.ai.api_key if config.ai else "",
        "base_url": config.ai.base_url if config.ai else "https://opencode.ai/zen/go/v1",
        "model": config.ai.model if config.ai else "glm-5.1",
        "author": config.author,
        "area": config.area,
        "developer": config.developer,
        "worker_model": config.worker_model,
        "timeout": config.ai.timeout if config.ai else 300.0,
        "brand_name": config.brand_name,
        "brand_tagline": config.brand_tagline,
        "brand_logo": config.brand_logo,
    }

    def _persist() -> None:
        save_config(
            CONFIG_PATH,
            db_path=config.db_path,
            api_key=state["api_key"],
            base_url=state["base_url"],
            model=state["model"],
            author=state["author"],
            area=state["area"],
            developer=state["developer"],
            worker_model=state["worker_model"],
            timeout=state["timeout"],
            brand_name=state["brand_name"],
            brand_tagline=state["brand_tagline"],
            brand_logo=state["brand_logo"],
        )

    # --- Callback: configurar IA en caliente desde la UI ---
    def configure_ai(api_key: str, base_url: str, model: str, worker_model: str = "") -> None:
        provider = OpenAICompatibleProvider(
            AIConfig(api_key=api_key, base_url=base_url, model=model, timeout=state["timeout"])
        )
        service.set_ai(provider)  # se activa al instante, sin reiniciar
        service.set_worker_ai(_worker_provider(api_key, base_url, worker_model, state["timeout"]))
        state.update(api_key=api_key, base_url=base_url, model=model, worker_model=worker_model)
        _persist()

    # --- Callback: listar los modelos disponibles de una conexión ---
    def list_models(api_key: str, base_url: str) -> list[str]:
        return list_available_models(api_key, base_url)

    # --- Callback: recordar el autor (para el versionamiento) ---
    def set_author(name: str) -> None:
        state["author"] = name
        _persist()

    # --- Callback: recordar el área (para los Datos generales) ---
    def set_area(area: str) -> None:
        state["area"] = area
        _persist()

    # --- Callback: recordar el desarrollador (autor del versionamiento) ---
    def set_developer(developer: str) -> None:
        state["developer"] = developer
        _persist()

    # --- Callback: identidad del documento (marca/lema/logo del PDF) ---
    def set_identity(brand: str, tagline: str, logo: str) -> None:
        renderer.set_identity(brand, tagline, logo)  # aplica al instante (PDF)
        docx_renderer.set_identity(brand, tagline, logo)  # y Word
        state.update(brand_name=brand, brand_tagline=tagline, brand_logo=logo)
        _persist()

    initial_ai = (
        {
            "api_key": config.ai.api_key, "base_url": config.ai.base_url,
            "model": config.ai.model, "worker_model": config.worker_model,
        }
        if config.ai
        else {"worker_model": config.worker_model}
    )

    # --- Presentación ---
    from src.presentation.main_window import MainWindow

    from src.presentation.theme import STYLESHEET

    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # base consistente que respeta el QSS en todas las plataformas
    app.setStyleSheet(STYLESHEET)
    window = MainWindow(
        service,
        configure_ai=configure_ai,
        initial_ai=initial_ai,
        initial_author=config.author,
        on_set_author=set_author,
        initial_area=config.area,
        on_set_area=set_area,
        initial_developer=config.developer,
        on_set_developer=set_developer,
        list_models=list_models,
        initial_identity={
            "brand": config.brand_name,
            "tagline": config.brand_tagline,
            "logo": config.brand_logo,
        },
        on_set_identity=set_identity,
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
