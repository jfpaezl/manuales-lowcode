"""Diálogo de configuración de la conexión de IA."""
from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)

# Presets cómodos. Cada uno: (base_url, modelo orquestador, modelo obrero).
# Todos hablan el protocolo OpenAI-compatible (Anthropic y Google vía su capa de
# compatibilidad). El usuario igual puede escribir cualquier endpoint y modelo.
# OJO: los IDs de modelo cambian seguido — verificá los exactos en tu proveedor.
_PRESETS = {
    "OpenCode Go": ("https://opencode.ai/zen/go/v1", "glm-5.1", ""),
    "OpenCode Zen": ("https://opencode.ai/zen/v1", "opencode/big-pickle", ""),
    "OpenAI": ("https://api.openai.com/v1", "gpt-4o", "gpt-4o-mini"),
    "Anthropic (Claude)": (
        "https://api.anthropic.com/v1/", "claude-sonnet-4-6", "claude-haiku-4-5-20251001",
    ),
    "Google (Gemini)": (
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "gemini-2.5-pro", "gemini-2.5-flash",
    ),
    "OpenRouter": ("https://openrouter.ai/api/v1", "openai/gpt-4o", "openai/gpt-4o-mini"),
    "Ollama (local)": ("http://localhost:11434/v1", "llama3.1", ""),
    "Otro / manual": ("", "", ""),
}


class SettingsDialog(QDialog):
    def __init__(
        self, parent=None, *, api_key="", base_url="", model="", worker_model="",
        list_models: Callable[[str, str], list[str]] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configuración de IA")
        self.setMinimumWidth(520)
        self._list_models = list_models

        self._preset = QComboBox()
        self._preset.addItems(_PRESETS.keys())
        self._preset.currentTextChanged.connect(self._apply_preset)

        self._api_key = QLineEdit(api_key)
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key.setPlaceholderText("Tu API key (OpenAI, Anthropic, Google, OpenCode…)")

        self._base_url = QLineEdit(base_url or "https://opencode.ai/zen/go/v1")

        # Modelo principal y obrero: combos EDITABLES. La lista se llena al tocar
        # «Cargar modelos», pero siempre podés escribir el ID a mano.
        self._model = QComboBox()
        self._model.setEditable(True)
        self._model.setCurrentText(model or "glm-5.1")

        self._worker_model = QComboBox()
        self._worker_model.setEditable(True)
        self._worker_model.setCurrentText(worker_model)
        self._worker_model.lineEdit().setPlaceholderText(
            "Opcional: modelo chico/barato (ej: gpt-4o-mini)"
        )

        self._load_btn = QPushButton("🔄 Cargar modelos disponibles")
        self._load_btn.setToolTip("Consulta a la conexión qué modelos ofrece (necesita API key)")
        self._load_btn.clicked.connect(self._on_load_models)

        info = QLabel(
            "Elegí un proveedor y pegá su API key. Funcionan OpenCode, OpenAI, "
            "Anthropic (Claude) y Google (Gemini) — estos dos últimos vía su capa "
            "OpenAI-compatible. Tocá «Cargar modelos» para ver los disponibles, o "
            "escribí el ID a mano."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #52606d;")

        worker_info = QLabel(
            "El «Modelo obrero» (opcional) se usa para generar paquetes grandes "
            "(Solutions) repartiendo el trabajo: el modelo principal orquesta y el "
            "obrero —más barato— redacta cada componente. Si lo dejás vacío, se usa "
            "el modelo principal para todo."
        )
        worker_info.setWordWrap(True)
        worker_info.setStyleSheet("color: #52606d;")

        form = QFormLayout(self)
        form.addRow(info)
        form.addRow("Proveedor", self._preset)
        form.addRow("API key", self._api_key)
        form.addRow("Base URL", self._base_url)
        form.addRow("", self._load_btn)
        form.addRow("Modelo principal (orquestador)", self._model)
        form.addRow("Modelo obrero", self._worker_model)
        form.addRow(worker_info)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Guardar y activar")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _apply_preset(self, name: str) -> None:
        url, model, worker = _PRESETS.get(name, ("", "", ""))
        if url:
            self._base_url.setText(url)
            self._model.setCurrentText(model)
            self._worker_model.setCurrentText(worker)

    def _on_load_models(self) -> None:
        if self._list_models is None:
            return
        from PyQt6.QtWidgets import QMessageBox

        api_key = self._api_key.text().strip()
        base_url = self._base_url.text().strip()
        if not api_key or not base_url:
            QMessageBox.warning(self, "Modelos", "Poné la API key y la Base URL primero.")
            return

        self._load_btn.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        models = None
        error = ""
        try:
            models = self._list_models(api_key, base_url)
        except Exception as exc:  # noqa: BLE001 — el proveedor puede no soportar /models
            error = str(exc)
        finally:
            QApplication.restoreOverrideCursor()
            self._load_btn.setEnabled(True)

        if models is None:
            QMessageBox.warning(
                self, "Modelos",
                f"No pude listar los modelos de esta conexión:\n\n{error}\n\n"
                "Podés escribir el ID del modelo a mano.",
            )
            return
        if not models:
            QMessageBox.information(
                self, "Modelos",
                "La conexión no devolvió modelos. Escribí el ID a mano.",
            )
            return

        self._fill_combo(self._model, models)
        self._fill_combo(self._worker_model, models)
        QMessageBox.information(
            self, "Modelos",
            f"Se cargaron {len(models)} modelos. Elegí uno en cada lista "
            "(la lista puede incluir modelos que no son de chat).",
        )

    @staticmethod
    def _fill_combo(combo: QComboBox, models: list[str]) -> None:
        current = combo.currentText()  # preservar lo ya elegido/escrito
        combo.clear()
        combo.addItems(models)
        combo.setCurrentText(current)

    def _on_accept(self) -> None:
        if not self._api_key.text().strip():
            self._api_key.setPlaceholderText("⚠ La API key es obligatoria")
            return
        if not self._base_url.text().strip():
            return
        self.accept()

    def values(self) -> dict:
        return {
            "api_key": self._api_key.text().strip(),
            "base_url": self._base_url.text().strip(),
            "model": self._model.currentText().strip() or "glm-5.1",
            "worker_model": self._worker_model.currentText().strip(),
        }
