"""Diálogo para configurar la identidad de marca del PDF: nombre, lema y logo.

Esta identidad aparece en la PORTADA de los manuales generados. Reemplaza lo
que antes estaba hardcodeado en el renderer.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)


class IdentityDialog(QDialog):
    def __init__(self, parent=None, *, brand="", tagline="", logo="") -> None:
        super().__init__(parent)
        self.setWindowTitle("Identidad del documento")
        self.setMinimumWidth(480)
        self._logo_path = logo

        self._brand = QLineEdit(brand)
        self._brand.setPlaceholderText("Nombre de tu empresa/marca (ej: Mi Empresa S.A.)")
        self._tagline = QLineEdit(tagline)
        self._tagline.setPlaceholderText("Lema o subtítulo (opcional)")

        self._logo_label = QLabel(self._logo_text())
        self._logo_label.setWordWrap(True)
        btn_logo = QPushButton("Elegir logo…")
        btn_logo.clicked.connect(self._pick_logo)
        btn_clear = QPushButton("Quitar")
        btn_clear.clicked.connect(self._clear_logo)
        logo_row = QHBoxLayout()
        logo_row.addWidget(self._logo_label, 1)
        logo_row.addWidget(btn_logo)
        logo_row.addWidget(btn_clear)
        logo_w = QWidget()
        logo_w.setLayout(logo_row)

        info = QLabel(
            "Esta identidad aparece en la PORTADA de los PDF que generes. El logo se "
            "incrusta en el PDF; si después movés el archivo, volvé a elegirlo."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #52606d;")

        form = QFormLayout(self)
        form.addRow(info)
        form.addRow("Marca / Empresa", self._brand)
        form.addRow("Lema (tagline)", self._tagline)
        form.addRow("Logo", logo_w)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Guardar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _logo_text(self) -> str:
        return Path(self._logo_path).name if self._logo_path else "(sin logo)"

    def _pick_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Elegí el logo", "", "Imágenes (*.png *.jpg *.jpeg)"
        )
        if path:
            self._logo_path = path
            self._logo_label.setText(self._logo_text())

    def _clear_logo(self) -> None:
        self._logo_path = ""
        self._logo_label.setText(self._logo_text())

    def values(self) -> dict:
        return {
            "brand": self._brand.text().strip(),
            "tagline": self._tagline.text().strip(),
            "logo": self._logo_path.strip(),
        }
