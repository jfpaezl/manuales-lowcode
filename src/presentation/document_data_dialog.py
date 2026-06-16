"""Diálogo de datos del documento: responsable, desarrollador, área y fecha.

Los aporta el USUARIO (la IA no los inventa). Dos roles DISTINTOS:
- «Responsable»: quien EJECUTA/opera la automatización → Datos generales.
- «Desarrollador»: quien PROGRAMÓ el flujo → autor del Versionamiento.
La fecha viene pre-cargada con hoy, pero es editable. El campo «Área» solo se
muestra para manuales funcionales (los técnicos no tienen «Datos generales»);
el «Desarrollador» se muestra siempre (Versionamiento está en ambos tipos).
"""
from __future__ import annotations

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
)


class DocumentDataDialog(QDialog):
    def __init__(
        self, parent=None, *, author: str = "", area: str = "", developer: str = "",
        show_area: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Datos del documento")
        self.setMinimumWidth(380)
        self._show_area = show_area

        self._author = QLineEdit(author)
        self._author.setPlaceholderText("Quién ejecuta/opera la automatización")

        self._developer = QLineEdit(developer)
        self._developer.setPlaceholderText("Quién desarrolló el flujo")

        self._area = QLineEdit(area)
        self._area.setPlaceholderText("Ej: Finanzas, RRHH, Operaciones")

        self._fecha = QDateEdit()
        self._fecha.setCalendarPopup(True)
        self._fecha.setDisplayFormat("dd/MM/yyyy")
        self._fecha.setDate(QDate.currentDate())  # hoy por defecto, editable

        form = QFormLayout(self)
        form.addRow("Responsable", self._author)
        if show_area:
            form.addRow("Área", self._area)
        form.addRow("Desarrollador", self._developer)
        form.addRow("Fecha", self._fecha)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> dict:
        return {
            "author": self._author.text().strip(),
            "developer": self._developer.text().strip(),
            "area": self._area.text().strip() if self._show_area else "",
            "fecha": self._fecha.date().toString("dd/MM/yyyy"),
        }
