"""Diálogo de importación de paquete: genera un manual FUNCIONAL y uno TÉCNICO.

Una sola importación produce los dos manuales (en dos PDFs distintos). Acá se
elige el título base, la categoría y los datos del documento (responsable, área,
fecha) que se usan en ambos.
"""
from __future__ import annotations

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
)


class ImportDialog(QDialog):
    def __init__(
        self, parent=None, *, package_name="", categories=None, author="", area="",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Importar paquete → manual funcional + técnico")
        self.setMinimumWidth(460)

        info = QLabel(
            "De este paquete se generan DOS manuales —funcional y técnico—, cada uno "
            "con su propio PDF. Quedan como borrador para que los revises y guardes."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #52606d;")

        self._title = QLineEdit(package_name)
        self._title.setPlaceholderText("Título base (se le agrega «(Funcional)» / «(Técnico)»)")

        self._cat = QComboBox()
        for label in (categories or ["Otro"]):
            self._cat.addItem(label, label)

        self._author = QLineEdit(author)
        self._author.setPlaceholderText("Responsable/autor")
        self._area = QLineEdit(area)
        self._area.setPlaceholderText("Área/sector (para el manual funcional)")

        self._fecha = QDateEdit()
        self._fecha.setCalendarPopup(True)
        self._fecha.setDisplayFormat("dd/MM/yyyy")
        self._fecha.setDate(QDate.currentDate())

        form = QFormLayout(self)
        form.addRow(info)
        form.addRow("Título base", self._title)
        form.addRow("Categoría", self._cat)
        form.addRow("Responsable", self._author)
        form.addRow("Área", self._area)
        form.addRow("Fecha", self._fecha)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Generar ambos")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _on_accept(self) -> None:
        if not self._title.text().strip():
            self._title.setPlaceholderText("⚠ El título base es obligatorio")
            return
        self.accept()

    def values(self) -> dict:
        return {
            "title": self._title.text().strip(),
            "categoria": self._cat.currentData(),
            "author": self._author.text().strip(),
            "area": self._area.text().strip(),
            "fecha": self._fecha.date().toString("dd/MM/yyyy"),
        }
