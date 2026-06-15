"""Diálogo para completar los huecos [COMPLETAR] del manual.

Muestra una pregunta (redactada por la IA) por cada hueco, con su campo. Lo que
el usuario deje vacío queda como [COMPLETAR] (no se rellena a ojo).
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
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
        self.setMinimumSize(580, 440)
        self._fields: list[QLineEdit] = []

        intro = QLabel(
            f"Hay {len(questions)} dato(s) por completar. Respondé lo que sepas; "
            "lo que dejes vacío queda como [COMPLETAR]."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #52606d; margin-bottom: 4px;")

        # Contenido scrolleable: cada pregunta numerada (negrita) + su campo.
        inner = QWidget()
        col = QVBoxLayout(inner)
        col.setSpacing(2)
        col.setContentsMargins(2, 2, 14, 2)  # margen derecho: aire para la scrollbar

        for i, q in enumerate(questions, 1):
            label = QLabel(f"{i}.  {q}")
            label.setWordWrap(True)
            label.setStyleSheet("font-weight: 600; color: #15192C; margin-top: 12px;")
            field = QLineEdit()
            field.setPlaceholderText("Tu respuesta… (dejá vacío si no la sabés)")
            self._fields.append(field)
            col.addWidget(label)
            col.addWidget(field)
        col.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)  # sin recuadro: más limpio con el tema
        scroll.setWidget(inner)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Rellenar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)        # intro fijo arriba (fuera del scroll)
        layout.addWidget(scroll, 1)
        layout.addWidget(buttons)

    def answers(self) -> list[str]:
        return [f.text().strip() for f in self._fields]
