"""Diálogo unificado para crear un manual con IA: genera funcional Y técnico.

La FUENTE se elige acá mismo (es el corazón del manual): un TEMA escrito, o un
PAQUETE exportado (.zip/.msapp/.xlsm). El resto de los datos (título, categoría,
responsable…) son comunes. Al terminar se crean las DOS partes como borradores."""
from __future__ import annotations

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

_FILE_FILTER = "Paquete (*.zip *.msapp *.xlsm *.pbit *.pbix)"

# Ayuda para exportar bien cada origen (sobre todo Power BI, que necesita el .pbit).
_EXPORT_HELP = (
    "ℹ️ Cómo exportar para que se pueda leer:\n"
    "• Power BI → Archivo → Exportar → Plantilla de Power BI (.pbit). "
    "El .pbix NO sirve para el modelo/medidas (viene comprimido); el .pbit trae "
    "tablas, medidas DAX y relaciones.\n"
    "• Power Automate / Power Apps → exportá la Solución o el flujo/app como .zip.\n"
    "• Excel (macros / Power Query) → guardá el libro como .xlsm."
)


class NewManualDialog(QDialog):
    def __init__(
        self, parent=None, *, categories: list[str] | None = None,
        author: str = "", area: str = "", developer: str = "", source_default: str = "topic",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Crear manual con IA → funcional + técnico")
        self.setMinimumWidth(500)
        self._file_path = ""

        info = QLabel(
            "Elegí DE QUÉ generar el manual (un tema, o un paquete exportado) y la IA "
            "arma DOS manuales —funcional y técnico—, cada uno con su PDF."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #52606d;")

        # --- Selector de fuente ---
        self._src_topic = QRadioButton("Desde un tema escrito")
        self._src_pkg = QRadioButton("Desde un paquete (.zip / .msapp / .xlsm / .pbit)")
        (self._src_pkg if source_default == "package" else self._src_topic).setChecked(True)
        self._src_topic.toggled.connect(self._update_source)
        src_row = QHBoxLayout()
        src_row.addWidget(self._src_topic)
        src_row.addWidget(self._src_pkg)

        # --- Fuente: TEMA ---
        self._topic_box = QWidget()
        topic_form = QFormLayout(self._topic_box)
        topic_form.setContentsMargins(0, 0, 0, 0)
        self._topic = QPlainTextEdit()
        self._topic.setPlaceholderText("¿Qué querés documentar? Ej: «Aprobación de facturas en Power Apps»")
        self._topic.setFixedHeight(64)
        self._context = QPlainTextEdit()
        self._context.setPlaceholderText("Contexto adicional para la IA (opcional)")
        self._context.setFixedHeight(52)
        topic_form.addRow("Tema", self._topic)
        topic_form.addRow("Contexto", self._context)

        # --- Fuente: PAQUETE ---
        self._pkg_box = QWidget()
        pkg_layout = QVBoxLayout(self._pkg_box)
        pkg_layout.setContentsMargins(0, 0, 0, 0)
        pkg_row = QHBoxLayout()
        self._pick_btn = QPushButton("📂 Elegir archivo…")
        self._pick_btn.clicked.connect(self._pick_file)
        self._file_label = QLabel("(ningún archivo elegido)")
        self._file_label.setStyleSheet("color: #52606d;")
        pkg_row.addWidget(self._pick_btn)
        pkg_row.addWidget(self._file_label, 1)
        pkg_layout.addLayout(pkg_row)
        # Comentario de cómo exportar cada origen (clave para Power BI: .pbit, no .pbix).
        pkg_help = QLabel(_EXPORT_HELP)
        pkg_help.setWordWrap(True)
        pkg_help.setStyleSheet("color: #52606d; font-size: 11px; background: #f5f7fa; padding: 6px;")
        pkg_layout.addWidget(pkg_help)

        # --- Datos comunes ---
        common = QWidget()
        form = QFormLayout(common)
        form.setContentsMargins(0, 0, 0, 0)
        self._title = QLineEdit()
        self._title.setPlaceholderText("Título base (en paquete, si lo dejás vacío usa el nombre del paquete)")
        self._cat = QComboBox()
        for label in categories or ["Otro"]:
            self._cat.addItem(label, label)
        self._author = QLineEdit(author)
        self._author.setPlaceholderText("Quién ejecuta/opera (responsable)")
        self._developer = QLineEdit(developer)
        self._developer.setPlaceholderText("Quién desarrolló (autor del versionamiento)")
        self._area = QLineEdit(area)
        self._area.setPlaceholderText("Área/sector (para el manual funcional)")
        self._fecha = QDateEdit()
        self._fecha.setCalendarPopup(True)
        self._fecha.setDisplayFormat("dd/MM/yyyy")
        self._fecha.setDate(QDate.currentDate())
        form.addRow("Título base", self._title)
        form.addRow("Categoría", self._cat)
        form.addRow("Responsable", self._author)
        form.addRow("Área", self._area)
        form.addRow("Desarrollador", self._developer)
        form.addRow("Fecha", self._fecha)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Generar ambos")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        outer = QVBoxLayout(self)
        outer.addWidget(info)
        outer.addLayout(src_row)
        outer.addWidget(self._topic_box)
        outer.addWidget(self._pkg_box)
        outer.addWidget(common)
        outer.addWidget(buttons)

        self._update_source()

    def _update_source(self) -> None:
        is_topic = self._src_topic.isChecked()
        self._topic_box.setVisible(is_topic)
        self._pkg_box.setVisible(not is_topic)

    def _pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Elegí el paquete a importar", "", _FILE_FILTER
        )
        if path:
            self._file_path = path
            self._file_label.setText(path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])

    def _on_accept(self) -> None:
        if self._src_topic.isChecked():
            if not self._title.text().strip():
                self._title.setPlaceholderText("⚠ El título base es obligatorio")
                return
            if not self._topic.toPlainText().strip():
                self._topic.setPlaceholderText("⚠ Decí qué querés documentar")
                return
        elif not self._file_path:
            self._file_label.setText("⚠ Elegí un archivo")
            return
        self.accept()

    def values(self) -> dict:
        return {
            "source": "topic" if self._src_topic.isChecked() else "package",
            "topic": self._topic.toPlainText().strip(),
            "context": self._context.toPlainText().strip(),
            "file_path": self._file_path,
            "title": self._title.text().strip(),
            "categoria": self._cat.currentData(),
            "author": self._author.text().strip(),
            "developer": self._developer.text().strip(),
            "area": self._area.text().strip(),
            "fecha": self._fecha.date().toString("dd/MM/yyyy"),
        }
