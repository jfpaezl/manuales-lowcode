"""Diálogo para completar los huecos [COMPLETAR] del manual.

Muestra una pregunta (redactada por la IA) por cada hueco, con su campo. Lo que
el usuario deje vacío queda como [COMPLETAR] (no se rellena a ojo).
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class PendingDialog(QDialog):
    def __init__(self, parent=None, *, questions: list[str]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Completar pendientes")
        self.setMinimumWidth(540)
        self.setMinimumHeight(360)
        self._fields: list[QLineEdit] = []

        inner = QWidget()
        col = QVBoxLayout(inner)
        intro = QLabel("Respondé lo que sepas. Lo que dejes vacío queda como [COMPLETAR].")
        intro.setWordWrap(True)
        col.addWidget(intro)

        for q in questions:
            label = QLabel(q)
            label.setWordWrap(True)
            label.setStyleSheet("font-weight: bold; margin-top: 6px;")
            field = QLineEdit()
            self._fields.append(field)
            col.addWidget(label)
            col.addWidget(field)
        col.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Rellenar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def answers(self) -> list[str]:
        return [f.text().strip() for f in self._fields]
