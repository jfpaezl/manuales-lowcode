"""ABM de categorías: crear, renombrar y borrar desde la app."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..application.manual_service import ManualService


class _CategoryEditDialog(QDialog):
    """Mini-form para crear o editar una categoría (etiqueta + pista de IA)."""

    def __init__(self, parent=None, *, label="", ai_hint="", title="Categoría") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)

        self._label = QLineEdit(label)
        self._label.setPlaceholderText("Ej: Power Automate")
        self._hint = QLineEdit(ai_hint)
        self._hint.setPlaceholderText("Cómo describírsela a la IA (ej: flujos de Power Automate)")

        form = QFormLayout(self)
        form.addRow("Etiqueta", self._label)
        form.addRow("Pista para la IA", self._hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _on_accept(self) -> None:
        if not self._label.text().strip():
            self._label.setPlaceholderText("⚠ La etiqueta es obligatoria")
            return
        self.accept()

    def values(self) -> dict:
        return {"label": self._label.text().strip(), "ai_hint": self._hint.text().strip()}


class CategoriesDialog(QDialog):
    def __init__(self, service: ManualService, parent=None) -> None:
        super().__init__(parent)
        self._svc = service
        self.setWindowTitle("Categorías")
        self.setMinimumSize(460, 380)

        self._list = QListWidget()

        row = QHBoxLayout()
        btn_new = QPushButton("➕ Nueva")
        btn_new.clicked.connect(self._on_new)
        btn_edit = QPushButton("✏ Renombrar")
        btn_edit.clicked.connect(self._on_edit)
        btn_del = QPushButton("🗑 Borrar")
        btn_del.clicked.connect(self._on_delete)
        row.addWidget(btn_new)
        row.addWidget(btn_edit)
        row.addWidget(btn_del)

        layout = QVBoxLayout(self)
        layout.addWidget(self._list)
        layout.addLayout(row)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.accept)
        close.accepted.connect(self.accept)
        layout.addWidget(close)

        self._refresh()

    def _refresh(self) -> None:
        self._list.clear()
        for c in self._svc.list_categories():
            text = c.label if not c.ai_hint else f"{c.label}   —   {c.ai_hint}"
            item = QListWidgetItem(text)
            item.setData(0x0100, c.label)  # Qt.UserRole == 0x0100
            self._list.addItem(item)

    def _selected_label(self) -> str | None:
        item = self._list.currentItem()
        return item.data(0x0100) if item else None

    def _on_new(self) -> None:
        dlg = _CategoryEditDialog(self, title="Nueva categoría")
        if not dlg.exec():
            return
        v = dlg.values()
        try:
            self._svc.add_category(v["label"], v["ai_hint"])
        except (ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "No se pudo crear", str(exc))
            return
        self._refresh()

    def _on_edit(self) -> None:
        label = self._selected_label()
        if not label:
            return
        current = next((c for c in self._svc.list_categories() if c.label == label), None)
        dlg = _CategoryEditDialog(
            self,
            label=label,
            ai_hint=current.ai_hint if current else "",
            title="Renombrar categoría",
        )
        if not dlg.exec():
            return
        v = dlg.values()
        try:
            self._svc.rename_category(label, v["label"], v["ai_hint"])
        except (ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "No se pudo renombrar", str(exc))
            return
        self._refresh()

    def _on_delete(self) -> None:
        label = self._selected_label()
        if not label:
            return
        ok = QMessageBox.question(self, "Borrar", f"¿Borrar la categoría '{label}'?")
        if ok != QMessageBox.StandardButton.Yes:
            return
        try:
            self._svc.delete_category(label)
        except (ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "No se puede borrar", str(exc))
            return
        self._refresh()
