"""Worker en hilo aparte para llamar a la IA sin congelar la UI.

Las llamadas a la IA tardan segundos. Si las corrés en el hilo principal,
la ventana se congela ("no responde"). Por eso van en un QThread.
"""
from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QThread, pyqtSignal


class AIWorker(QThread):
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)
    progress = pyqtSignal(str)  # avance parcial (ej: «componente 3/10») para la UI

    def __init__(self, fn: Callable[[], str]) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            self.finished_ok.emit(self._fn())
        except Exception as exc:  # noqa: BLE001 — la UI muestra el error
            self.failed.emit(str(exc))


class TaskWorker(QThread):
    """Worker genérico para tareas que NO devuelven texto y pueden tardar (ej:
    leer + extraer un .zip → ExtractedPackage). Mismo patrón que AIWorker, pero el
    resultado es `object`, así no congela la UI mientras se parsea un paquete grande."""
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn: Callable[[], object]) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            self.finished_ok.emit(self._fn())
        except Exception as exc:  # noqa: BLE001 — la UI muestra el error
            self.failed.emit(str(exc))
