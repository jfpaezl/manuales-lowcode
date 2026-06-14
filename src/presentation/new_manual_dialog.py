"""Diálogo para crear un manual nuevo."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPlainTextEdit,
)

from ..domain.entities import ManualType

_TIPOS = [("Funcional", ManualType.FUNCIONAL), ("Técnico", ManualType.TECNICO)]


class NewManualDialog(QDialog):
    def __init__(self, parent=None, *, categories: list[str] | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nuevo manual")
        self.setMinimumWidth(420)

        self._title = QLineEdit()
        self._title.setPlaceholderText("Ej: Aprobación de facturas en Power Apps")
        self._tipo = QComboBox()
        for label, value in _TIPOS:
            self._tipo.addItem(label, value)
        self._cat = QComboBox()
        for label in categories or ["Otro"]:
            self._cat.addItem(label, label)  # data == label (string)
        self._desc = QPlainTextEdit()
        self._desc.setPlaceholderText("Descripción breve (opcional)")
        self._desc.setFixedHeight(70)

        form = QFormLayout(self)
        form.addRow("Título", self._title)
        form.addRow("Tipo", self._tipo)
        form.addRow("Categoría", self._cat)
        form.addRow("Descripción", self._desc)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _on_accept(self) -> None:
        if not self._title.text().strip():
            self._title.setPlaceholderText("⚠ El título es obligatorio")
            return
        self.accept()

    def values(self) -> dict:
        return {
            "title": self._title.text().strip(),
            "tipo": self._tipo.currentData(),
            "categoria": self._cat.currentData(),
            "description": self._desc.toPlainText().strip(),
        }
