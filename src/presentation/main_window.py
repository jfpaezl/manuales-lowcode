"""Ventana principal. Habla SOLO con ManualService."""
from __future__ import annotations

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtPdfWidgets import QPdfView
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from collections.abc import Callable

from ..application.manual_service import ManualService
from ..domain.entities import Manual, ManualType
from .ai_worker import AIWorker, TaskWorker
from .categories_dialog import CategoriesDialog
from .document_data_dialog import DocumentDataDialog
from .identity_dialog import IdentityDialog
from .new_manual_dialog import NewManualDialog
from .pending_dialog import PendingDialog
from .settings_dialog import SettingsDialog

_AI_MODES = [
    ("Generar manual desde cero", "generate"),
    ("Documentar código pegado", "document_code"),
    ("Transcripción → manual", "transcription"),
    ("Complementar manual actual", "complement"),
]

# El cuadro de texto de la IA adapta su placeholder según el modo elegido.
_AI_PLACEHOLDERS = {
    "generate": "Tema u objeto a documentar (ej: «Aprobación de facturas en Power Apps»)…",
    "document_code": "Pegá acá el código a documentar (VBA, Power Fx, Python…)…",
    "transcription": "Pegá la transcripción de la explicación hablada…",
    "complement": "Qué agregar o corregir en el manual actual (ej: «agregá que avisa por Teams»)…",
}


class MainWindow(QMainWindow):
    def __init__(
        self,
        service: ManualService,
        *,
        configure_ai: Callable[[str, str, str, str], None] | None = None,
        initial_ai: dict | None = None,
        initial_author: str = "",
        on_set_author: Callable[[str], None] | None = None,
        initial_area: str = "",
        on_set_area: Callable[[str], None] | None = None,
        initial_developer: str = "",
        on_set_developer: Callable[[str], None] | None = None,
        list_models: Callable[[str, str], list[str]] | None = None,
        initial_identity: dict | None = None,
        on_set_identity: Callable[[str, str, str], None] | None = None,
    ) -> None:
        super().__init__()
        self._svc = service
        self._configure_ai = configure_ai
        self._list_models = list_models
        self._initial_ai = initial_ai or {}
        self._author = initial_author
        self._on_set_author = on_set_author
        self._area = initial_area
        self._on_set_area = on_set_area
        self._developer = initial_developer
        self._on_set_developer = on_set_developer
        self._identity = initial_identity or {}
        self._on_set_identity = on_set_identity
        self._current: Manual | None = None
        self._worker: AIWorker | None = None
        # Si True, el resultado de la IA reemplaza el editor; si False, se agrega abajo.
        self._ai_replace_editor = False
        # Estado del flujo "Completar pendientes" (entre la pregunta IA y el relleno).
        self._pending_base = ""
        self._pending_count = 0
        # Borradores generados por importación, aún sin guardar: manual_id -> markdown.
        self._drafts: dict[int, str] = {}
        # Estado de la importación dual en curso (funcional → técnico, en 2 pasos).
        self._import_ctx: dict = {}
        self._import_func_id: int | None = None
        self._import_tec_id: int | None = None
        # Datos del diálogo "Crear manual" mientras se extrae el paquete (fuente .zip).
        self._pending_create: dict = {}

        self.setWindowTitle("Manuales Low-Code")
        self.resize(1180, 760)

        self._build_menu()
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_sidebar())
        splitter.addWidget(self._build_editor())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 880])
        self.setCentralWidget(splitter)

        self.statusBar().showMessage("Listo.")
        self._setup_shortcuts()
        self._refresh_manual_list()
        self._set_editor_enabled(False)
        self._set_ai_enabled(self._svc.ai_ready)
        self._update_ai_placeholder()

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence.StandardKey.New, self, activated=lambda: self._open_create("topic"))  # Ctrl+N
        QShortcut(QKeySequence.StandardKey.Save, self, activated=self._on_save_version)  # Ctrl+S
        QShortcut(QKeySequence("F2"), self, activated=self._on_rename_manual)
        # Eliminar SOLO con la lista enfocada: no pisa el Supr al editar texto.
        del_sc = QShortcut(QKeySequence.StandardKey.Delete, self._list)
        del_sc.setContext(Qt.ShortcutContext.WidgetShortcut)
        del_sc.activated.connect(self._on_delete_manual)

    def _update_ai_placeholder(self, *_) -> None:
        mode = self._ai_mode.currentData()
        self._ai_input.setPlaceholderText(_AI_PLACEHOLDERS.get(mode, "…"))

    def _ai_busy(self, busy: bool) -> None:
        """Muestra/oculta la barra de progreso indeterminada de la IA y bloquea el
        botón de crear (no se arranca otra generación mientras hay una en curso)."""
        self._progress.setVisible(busy)
        self._new_btn.setEnabled(not busy)

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("⚙ Configuración")
        action = menu.addAction("Conexión de IA…")
        action.triggered.connect(self._open_settings)
        cat_action = menu.addAction("Categorías…")
        cat_action.triggered.connect(self._open_categories)
        brand_action = menu.addAction("Identidad del documento…")
        brand_action.triggered.connect(self._open_identity)

    def _open_identity(self) -> None:
        if self._on_set_identity is None:
            QMessageBox.information(self, "Identidad", "La configuración de identidad no está disponible.")
            return
        dlg = IdentityDialog(
            self,
            brand=self._identity.get("brand", ""),
            tagline=self._identity.get("tagline", ""),
            logo=self._identity.get("logo", ""),
        )
        if not dlg.exec():
            return
        vals = dlg.values()
        self._on_set_identity(vals["brand"], vals["tagline"], vals["logo"])
        self._identity = vals
        self.statusBar().showMessage("✓ Identidad del documento actualizada", 5000)

    def _open_categories(self) -> None:
        CategoriesDialog(self._svc, self).exec()
        # Las etiquetas pueden haber cambiado (rename) → refrescar la lista.
        self._refresh_manual_list()
        if self._current:
            self._current = self._svc.get_manual(self._current.id)
            if self._current:
                self._title_label.setText(
                    f"{self._current.title}  ·  {self._current.type.value} / {self._current.category}"
                )

    # --- Construcción de la UI -------------------------------------------

    def _build_sidebar(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        header = QLabel("Manuales")
        header.setObjectName("sidebarHeader")
        layout.addWidget(header)

        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_select_manual)
        layout.addWidget(self._list)

        row = QHBoxLayout()
        self._new_btn = QPushButton("✨ Nuevo (IA)")
        self._new_btn.setToolTip("Genera funcional + técnico desde un tema o un paquete (.zip)")
        self._new_btn.clicked.connect(lambda: self._open_create("topic"))
        btn_new = self._new_btn
        btn_rename = QPushButton("✏ Renombrar")
        btn_rename.clicked.connect(self._on_rename_manual)
        btn_del = QPushButton("🗑 Eliminar")
        btn_del.clicked.connect(self._on_delete_manual)
        row.addWidget(btn_new)
        row.addWidget(btn_rename)
        row.addWidget(btn_del)
        layout.addLayout(row)
        return w

    def _build_editor(self) -> QWidget:
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_edit_tab(), "✏ Editor")
        self._tabs.addTab(self._build_preview_tab(), "📄 Vista PDF")
        self._tabs.addTab(self._build_versions_tab(), "🕑 Versiones")
        self._activity_tab = self._build_activity_tab()
        self._tabs.addTab(self._activity_tab, "🔎 Actividad IA")
        return self._tabs

    def _build_edit_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        self._title_label = QLabel("Seleccioná o creá un manual")
        self._title_label.setObjectName("titleLabel")  # estilizado por el tema
        layout.addWidget(self._title_label)

        layout.addWidget(self._build_ai_box())

        layout.addWidget(QLabel("Contenido (Markdown):"))
        self._editor = QPlainTextEdit()
        self._editor.setPlaceholderText(
            "Escribí el manual en Markdown, o generalo con la IA de arriba.\n\n"
            "## Introducción\n...\n\n## Paso a paso\n1. ...\n"
        )
        layout.addWidget(self._editor)

        row = QHBoxLayout()
        self._change_note = QLineEdit()
        self._change_note.setPlaceholderText("Nota de cambio (qué cambió en esta versión)")
        row.addWidget(self._change_note)
        btn_save = QPushButton("💾 Guardar versión + PDF")
        btn_save.clicked.connect(self._on_save_version)
        row.addWidget(btn_save)
        layout.addLayout(row)
        return w

    def _build_ai_box(self) -> QWidget:
        box = QGroupBox("Asistente de IA")
        layout = QVBoxLayout(box)

        top = QHBoxLayout()
        self._ai_mode = QComboBox()
        for label, value in _AI_MODES:
            self._ai_mode.addItem(label, value)
        self._ai_mode.currentIndexChanged.connect(self._update_ai_placeholder)
        top.addWidget(self._ai_mode)
        self._ai_btn = QPushButton("✨ Generar con IA")
        self._ai_btn.clicked.connect(self._on_generate_ai)
        top.addWidget(self._ai_btn)
        self._ai_config_btn = QPushButton("⚙ Configurar IA…")
        self._ai_config_btn.clicked.connect(self._open_settings)
        top.addWidget(self._ai_config_btn)
        layout.addLayout(top)

        # Importar desde un paquete exportado (ej: flujo de Power Automate).
        # Extrae la estructura del ZIP y la manda a la IA para redactar el manual.
        pkg_row = QHBoxLayout()
        self._import_btn = QPushButton("📦 Crear desde ZIP (Power Automate / Power Apps)…")
        self._import_btn.clicked.connect(lambda: self._open_create("package"))
        pkg_row.addWidget(self._import_btn)
        self._complete_btn = QPushButton("✅ Completar pendientes")
        self._complete_btn.setToolTip("La IA te pregunta por cada [COMPLETAR] del manual")
        self._complete_btn.clicked.connect(self._on_complete_pending)
        pkg_row.addWidget(self._complete_btn)
        layout.addLayout(pkg_row)

        self._ai_input = QPlainTextEdit()
        self._ai_input.setPlaceholderText(
            "Tema a documentar, código a explicar, o transcripción de la explicación…"
        )
        self._ai_input.setFixedHeight(90)
        layout.addWidget(self._ai_input)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)        # indeterminada (va y viene)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(6)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._ai_status = QLabel("")
        self._ai_status.setStyleSheet("color: #16a085;")
        layout.addWidget(self._ai_status)
        return box

    def _build_activity_tab(self) -> QWidget:
        """Pestaña con el log EN VIVO de lo que la IA genera (el flujo dual ya no
        cae en el editor). Vive en su propia pestaña para no apretar al editor."""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("Lo que la IA va generando, en vivo:"))
        self._ai_log = QPlainTextEdit()
        self._ai_log.setReadOnly(True)
        self._ai_log.setPlaceholderText(
            "Cuando generes o importes, acá vas a ver lo que la IA produce mientras trabaja."
        )
        layout.addWidget(self._ai_log)
        return w

    def _ai_log_reset(self, header: str = "") -> None:
        self._ai_log.clear()
        if header:
            self._ai_log.appendPlainText(header)
        if hasattr(self, "_tabs"):  # traer la pestaña de actividad al frente
            self._tabs.setCurrentWidget(self._activity_tab)

    def _ai_log_append(self, text: str) -> None:
        self._ai_log.appendPlainText(text)
        sb = self._ai_log.verticalScrollBar()
        sb.setValue(sb.maximum())  # autoscroll al final

    def _set_ai_enabled(self, enabled: bool) -> None:
        """Prende o apaga el asistente según haya IA configurada."""
        self._ai_mode.setEnabled(enabled)
        self._ai_btn.setEnabled(enabled)
        self._ai_input.setEnabled(enabled)
        # Importar paquete necesita IA Y un extractor configurado.
        self._import_btn.setEnabled(enabled and self._svc.extractor_ready)
        # Completar pendientes necesita IA.
        self._complete_btn.setEnabled(enabled)
        if enabled:
            self._ai_status.setStyleSheet("color: #16a085;")
            self._ai_status.setText("✓ IA configurada y lista.")
        else:
            self._ai_status.setStyleSheet("color: #b45309;")
            self._ai_status.setText("⚠ IA no configurada. Tocá «⚙ Configurar IA…».")

    def _open_settings(self) -> None:
        if self._configure_ai is None:
            QMessageBox.information(self, "IA", "La configuración de IA no está disponible.")
            return
        dlg = SettingsDialog(
            self,
            api_key=self._initial_ai.get("api_key", ""),
            base_url=self._initial_ai.get("base_url", ""),
            model=self._initial_ai.get("model", ""),
            worker_model=self._initial_ai.get("worker_model", ""),
            list_models=self._list_models,
        )
        if not dlg.exec():
            return
        vals = dlg.values()
        try:
            self._configure_ai(
                vals["api_key"], vals["base_url"], vals["model"], vals["worker_model"]
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"No se pudo configurar la IA:\n{exc}")
            return
        self._initial_ai = vals
        self._set_ai_enabled(True)
        QMessageBox.information(self, "IA", "Conexión de IA guardada y activada. ¡Listo!")

    def _build_preview_tab(self) -> QWidget:
        self._pdf_doc = QPdfDocument(self)
        self._pdf_view = QPdfView(self)
        self._pdf_view.setDocument(self._pdf_doc)
        self._pdf_view.setPageMode(QPdfView.PageMode.MultiPage)

        w = QWidget()
        layout = QVBoxLayout(w)
        btn_export = QPushButton("⬇ Exportar PDF a disco…")
        btn_export.clicked.connect(self._on_export_pdf)
        layout.addWidget(btn_export)
        layout.addWidget(self._pdf_view)
        return w

    def _build_versions_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("Historial de versiones (doble clic para ver el PDF):"))
        self._versions = QListWidget()
        self._versions.itemDoubleClicked.connect(self._on_open_version)
        layout.addWidget(self._versions)
        return w

    # --- Manejo de estado -------------------------------------------------

    def _set_editor_enabled(self, enabled: bool) -> None:
        self._tabs.setEnabled(enabled)

    def _refresh_manual_list(self, select_id: int | None = None) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        manuals = self._svc.list_manuals()
        if not manuals:
            # Estado vacío: guía en vez de una lista en blanco.
            empty = QListWidgetItem("Todavía no hay manuales.\nTocá  ➕ Nuevo  para crear el primero.")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)  # no seleccionable
            empty.setForeground(Qt.GlobalColor.gray)
            self._list.addItem(empty)
        target_row = None
        for m in manuals:
            item = QListWidgetItem(f"{m.title}  ·  {m.type.value}")
            item.setData(Qt.ItemDataRole.UserRole, m.id)
            self._list.addItem(item)
            if select_id is not None and m.id == select_id:
                target_row = self._list.count() - 1
        self._list.blockSignals(False)
        if target_row is not None:
            self._list.setCurrentRow(target_row)  # dispara la selección (continuidad)

    def _on_select_manual(self, current: QListWidgetItem | None, _prev=None) -> None:
        if current is None:
            return
        manual_id = current.data(Qt.ItemDataRole.UserRole)
        self._current = self._svc.get_manual(manual_id)
        if self._current is None:
            return
        self._set_editor_enabled(True)
        self._title_label.setText(
            f"{self._current.title}  ·  {self._current.type.value} / {self._current.category}"
        )
        # Un borrador sin guardar (recién importado, o una actualización pendiente
        # sobre un manual que YA tiene versiones) es lo más fresco: tiene prioridad.
        # Si no hay borrador, cargamos el Markdown de la última versión para re-editar.
        latest = self._current.latest_version
        if self._current.id in self._drafts:
            self._editor.setPlainText(self._drafts[self._current.id])
        elif latest and latest.sections:
            self._editor.setPlainText(latest.sections[0].source_markdown)
        else:
            self._editor.clear()
        self._change_note.clear()
        self._refresh_versions()
        self._load_latest_pdf()

    def _refresh_versions(self) -> None:
        self._versions.clear()
        if not self._current:
            return
        for v in sorted(self._current.versions, key=lambda x: x.version, reverse=True):
            label = f"v{v.version}  ·  {v.created_at.strftime('%d/%m/%Y %H:%M')}"
            if v.change_note:
                label += f"  —  {v.change_note}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, v.id)
            self._versions.addItem(item)

    def _load_latest_pdf(self) -> None:
        if not self._current or not self._current.latest_version:
            self._pdf_doc.close()
            return
        self._show_pdf(self._current.latest_version.id)

    def _show_pdf(self, version_id: int | None) -> None:
        if version_id is None:
            return
        pdf = self._svc.get_version_pdf(version_id)
        if not pdf:
            self._pdf_doc.close()
            return
        self._pdf_bytes = QByteArray(pdf)  # mantener viva la referencia
        self._pdf_buffer = QBuffer(self._pdf_bytes)
        self._pdf_buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self._pdf_doc.load(self._pdf_buffer)

    # --- Acciones ---------------------------------------------------------

    def _open_create(self, source_default: str = "topic") -> None:
        """Diálogo unificado de creación: la FUENTE (tema o paquete .zip) se elige
        adentro. Genera funcional Y técnico con el MISMO motor dual."""
        if not self._svc.ai_ready:
            QMessageBox.warning(self, "Crear manual", "Configurá la IA antes de crear un manual.")
            return
        categories = [c.label for c in self._svc.list_categories()]
        dlg = NewManualDialog(
            self, categories=categories,
            author=self._author, area=self._area, developer=self._developer,
            source_default=source_default,
        )
        if not dlg.exec():
            return
        v = dlg.values()

        # Recordamos responsable/desarrollador/área para la próxima.
        self._author, self._area, self._developer = v["author"], v["area"], v["developer"]
        if self._on_set_author:
            self._on_set_author(self._author)
        if self._on_set_area:
            self._on_set_area(self._area)
        if self._on_set_developer:
            self._on_set_developer(self._developer)

        self._pending_create = v
        if v["source"] == "package":
            self._begin_extraction(v["file_path"])  # extrae y sigue en _on_extract_done
            return

        # Fuente TEMA: directo al motor dual.
        self._import_ctx = {
            "source": "topic",
            "topic": v["topic"], "context": v["context"],
            "hint": self._svc.category_hint(v["categoria"]),
            "author": v["author"], "area": v["area"], "fecha": v["fecha"],
            "developer": v["developer"],
            "title": v["title"], "categoria": v["categoria"],
            "diff": None, "update_func_id": None, "update_tec_id": None,
        }
        self._import_func_id = None
        self._import_tec_id = None
        self._start_import_step(ManualType.FUNCIONAL)

    def _on_rename_manual(self) -> None:
        if not self._current:
            QMessageBox.information(self, "Renombrar", "Seleccioná un manual primero.")
            return
        new_title, ok = QInputDialog.getText(
            self, "Renombrar manual", "Nuevo título:", text=self._current.title
        )
        if not ok:
            return
        try:
            self._svc.rename_manual(self._current.id, new_title)
        except ValueError as exc:
            QMessageBox.warning(self, "Renombrar", str(exc))
            return
        mid = self._current.id
        self._refresh_manual_list(select_id=mid)  # re-selecciona y refresca el título
        self.statusBar().showMessage("✓ Título actualizado", 5000)

    def _on_delete_manual(self) -> None:
        if not self._current:
            return
        ok = QMessageBox.question(
            self, "Eliminar", f"¿Borrar '{self._current.title}' y todas sus versiones?"
        )
        if ok == QMessageBox.StandardButton.Yes:
            title = self._current.title
            self._drafts.pop(self._current.id, None)
            self._svc.delete_manual(self._current.id)
            self._current = None
            self._refresh_manual_list()
            self._set_editor_enabled(False)
            self.statusBar().showMessage(f"🗑 «{title}» eliminado", 5000)

    def _on_save_version(self) -> None:
        if not self._current:
            return
        md = self._editor.toPlainText().strip()
        if not md:
            QMessageBox.warning(self, "Vacío", "El contenido está vacío.")
            return
        section = self._svc.markdown_to_section(title="", markdown_text=md)
        note = self._change_note.text().strip()
        try:
            self._svc.save_version(self._current.id, [section], note)
        except Exception as exc:  # noqa: BLE001 — probablemente GTK/WeasyPrint
            retry = QMessageBox.question(
                self,
                "No se pudo generar el PDF",
                f"Falló la generación del PDF:\n\n{exc}\n\n"
                "¿Guardar la versión SIN PDF? (instalá GTK para el PDF)",
            )
            if retry != QMessageBox.StandardButton.Yes:
                return
            self._svc.save_version(self._current.id, [section], note, generate_pdf=False)

        self._drafts.pop(self._current.id, None)  # ya guardado: deja de ser borrador
        self._current = self._svc.get_manual(self._current.id)
        latest = self._current.latest_version
        self._change_note.clear()
        self._refresh_versions()
        self._load_latest_pdf()
        self._tabs.setCurrentIndex(1)  # ir a la vista PDF
        num = latest.version if latest else "?"
        self.statusBar().showMessage(f"✓ Versión {num} guardada", 5000)

    def _on_open_version(self, item: QListWidgetItem) -> None:
        self._show_pdf(item.data(Qt.ItemDataRole.UserRole))
        self._tabs.setCurrentIndex(1)

    def _on_export_pdf(self) -> None:
        if not self._current or not self._current.latest_version:
            return
        pdf = self._svc.get_version_pdf(self._current.latest_version.id)
        if not pdf:
            QMessageBox.information(self, "Sin PDF", "Esta versión no tiene PDF generado.")
            return
        default = f"{self._current.title}_v{self._current.latest_version.version}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Exportar PDF", default, "PDF (*.pdf)")
        if path:
            with open(path, "wb") as f:
                f.write(pdf)
            QMessageBox.information(self, "Exportado", f"PDF guardado en:\n{path}")

    # --- IA ---------------------------------------------------------------

    def _ask_document_data(self, tipo: ManualType) -> dict | None:
        """Pide responsable, área (solo funcional) y fecha (hoy, editable).
        Persiste autor y área para la próxima. Devuelve None si se cancela."""
        dlg = DocumentDataDialog(
            self, author=self._author, area=self._area, developer=self._developer,
            show_area=(tipo is ManualType.FUNCIONAL),
        )
        if not dlg.exec():
            return None
        vals = dlg.values()
        self._author = vals["author"]
        if self._on_set_author:
            self._on_set_author(self._author)
        self._developer = vals["developer"]
        if self._on_set_developer:
            self._on_set_developer(self._developer)
        if tipo is ManualType.FUNCIONAL:
            self._area = vals["area"]
            if self._on_set_area:
                self._on_set_area(self._area)
        return vals

    def _on_generate_ai(self) -> None:
        if not self._current:
            QMessageBox.information(self, "IA", "Seleccioná un manual primero.")
            return
        text = self._ai_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "IA", "Escribí el tema, código, transcripción o lo que querés agregar.")
            return

        mode = self._ai_mode.currentData()
        tipo = self._current.type
        # Resolvemos el hint AHORA, en el hilo principal (acá vive la conexión
        # SQLite). El worker recibe solo texto, NO toca la base.
        hint = self._svc.category_hint(self._current.category)

        # Complementar necesita un manual ya existente en el editor como base.
        base = self._editor.toPlainText().strip()
        if mode == "complement" and not base:
            QMessageBox.warning(
                self, "IA",
                "No hay manual en el editor para complementar.\n"
                "Generá o importá uno primero, después complementalo.",
            )
            return

        # Modos que arman el manual desde cero: pedimos responsable, desarrollador, área y fecha.
        author, area, fecha, developer = self._author, self._area, "", self._developer
        if mode in ("generate", "transcription"):
            data = self._ask_document_data(tipo)
            if data is None:
                return
            author, area, fecha = data["author"], data["area"], data["fecha"]
            developer = data["developer"]

        # Complementar INTEGRA sobre lo existente → el resultado reemplaza el editor.
        self._ai_replace_editor = (mode == "complement")

        def call() -> str:
            if mode == "generate":
                return self._svc.ai_generate(
                    topic=text, tipo=tipo, categoria_hint=hint,
                    author=author, area=area, fecha=fecha, developer=developer,
                )
            if mode == "document_code":
                return self._svc.ai_document_code(code=text, tipo=tipo, categoria_hint=hint)
            if mode == "complement":
                return self._svc.ai_complement(
                    current_markdown=base, instructions=text, tipo=tipo, categoria_hint=hint,
                )
            return self._svc.ai_from_transcription(
                transcription=text, tipo=tipo, categoria_hint=hint,
                author=author, area=area, fecha=fecha, developer=developer,
            )

        self._ai_btn.setEnabled(False)
        self._ai_busy(True)
        self._ai_status.setText("Generando… (puede tardar unos segundos)")
        self._worker = AIWorker(call)
        self._worker.finished_ok.connect(self._on_ai_done)
        self._worker.failed.connect(self._on_ai_error)
        self._worker.start()

    def _begin_extraction(self, path: str) -> None:
        """Lee + parsea el paquete en un hilo (no congela la UI) y sigue en
        _on_extract_done. Los datos del documento ya vienen de _pending_create."""
        self._import_btn.setEnabled(False)
        self._ai_btn.setEnabled(False)
        self._ai_busy(True)
        nombre = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        self._ai_status.setText(f"📦 Leyendo y analizando «{nombre}»… (puede tardar en soluciones grandes)")
        self.statusBar().showMessage("Leyendo el paquete…")

        def read_and_extract() -> object:
            with open(path, "rb") as f:
                data = f.read()
            return self._svc.extract_package(data, path)

        self._worker = TaskWorker(read_and_extract)
        self._worker.finished_ok.connect(self._on_extract_done)
        self._worker.failed.connect(self._on_extract_error)
        self._worker.start()

    def _on_extract_error(self, message: str) -> None:
        self._ai_busy(False)
        self._ai_status.setText("")
        self.statusBar().clearMessage()
        self._import_btn.setEnabled(self._svc.extractor_ready)
        self._ai_btn.setEnabled(True)
        QMessageBox.critical(
            self, "No se pudo leer el paquete",
            f"No pude extraer la estructura del paquete:\n\n{message}",
        )

    def _on_extract_done(self, extracted) -> None:
        """Tras extraer (hilo principal): avisos, detección de re-import y arranque
        del motor dual. Los datos del documento ya los tomó el diálogo de creación."""
        v = self._pending_create
        self._ai_busy(False)
        self._ai_status.setText("✓ Paquete analizado.")
        self.statusBar().clearMessage()
        self._import_btn.setEnabled(self._svc.extractor_ready)
        self._ai_btn.setEnabled(True)

        if extracted.warnings:
            QMessageBox.warning(
                self, "Avisos al leer el paquete",
                "Leí el paquete, pero con advertencias:\n\n- " + "\n- ".join(extracted.warnings),
            )

        # ¿Ya importamos este paquete antes? (seguimiento de cambios entre versiones)
        update_diff, existing_ids = self._detect_reimport(extracted)

        self._import_ctx = {
            "source": "package",
            "extracted": extracted,
            "hint": self._svc.category_hint(v["categoria"]),
            "author": v["author"], "area": v["area"], "fecha": v["fecha"],
            "developer": v["developer"],
            # Si el título base quedó vacío, usamos el nombre del paquete.
            "title": v["title"] or extracted.name,
            "categoria": v["categoria"],
            # Seguimiento de cambios: si es actualización, el diff a marcar y a qué
            # manuales (funcional/técnico) agregarles versión en vez de crear otros.
            "diff": update_diff,
            "update_func_id": existing_ids[0] if existing_ids else None,
            "update_tec_id": existing_ids[1] if existing_ids else None,
        }
        self._import_func_id = None  # id del funcional una vez creado/encontrado
        self._import_tec_id = None
        self._start_import_step(ManualType.FUNCIONAL)

    def _detect_reimport(self, extracted):
        """¿Este paquete ya se importó? Si sí y hay cambios, ofrece actualizar los
        manuales existentes como nueva versión. Devuelve (diff|None, (func_id, tec_id)|None)."""
        stored = self._svc.find_snapshot(extracted.unique_name)
        if stored is None or stored.manual_func_id is None or stored.manual_tec_id is None:
            return None, None  # primera vez (o sin manuales ligados): flujo normal
        # Verificamos que los manuales sigan existiendo (pudieron borrarse).
        if self._svc.get_manual(stored.manual_func_id) is None or \
                self._svc.get_manual(stored.manual_tec_id) is None:
            return None, None
        diff = self._svc.diff_for(extracted)
        resumen = (
            f"{len(diff.deprecated)} deprecado(s), {len(diff.modified)} modificado(s), "
            f"{len(diff.added)} nuevo(s)"
        )
        ok = QMessageBox.question(
            self, "Esta solución ya existe",
            f"«{extracted.name}» ya fue importada (versión {diff.version_from}).\n"
            f"Nueva versión: {diff.version_to}. Cambios detectados: {resumen}.\n\n"
            "¿Actualizar los manuales existentes como NUEVA VERSIÓN, marcando lo "
            "deprecado y lo que cambió?\n\n"
            "(Si elegís No, se generan manuales nuevos desde cero, sin marcar cambios.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ok != QMessageBox.StandardButton.Yes:
            return None, None
        return diff, (stored.manual_func_id, stored.manual_tec_id)

    def _start_import_step(self, tipo: ManualType) -> None:
        """Motor de generación DUAL (funcional → técnico, en dos pasos). Lo usan
        tanto la importación de un paquete como la creación desde un tema escrito;
        la diferencia es solo de QUÉ generador se llama (según ctx["source"])."""
        ctx = self._import_ctx
        label = "funcional" if tipo is ManualType.FUNCIONAL else "técnico"
        extracted = ctx.get("extracted")
        n_comp = len(extracted.components) if extracted is not None else 1

        def call() -> str:
            if ctx["source"] == "package":
                return self._svc.ai_from_package(
                    extracted=ctx["extracted"], tipo=tipo, categoria_hint=ctx["hint"],
                    author=ctx["author"], area=ctx["area"], fecha=ctx["fecha"],
                    developer=ctx["developer"], diff=ctx["diff"],
                    progress=self._worker.progress.emit,  # reporta avance a la UI
                )
            return self._svc.ai_generate(
                topic=ctx["topic"], tipo=tipo, categoria_hint=ctx["hint"],
                author=ctx["author"], area=ctx["area"], fecha=ctx["fecha"],
                developer=ctx["developer"], context=ctx["context"],
            )

        self._ai_btn.setEnabled(False)
        self._import_btn.setEnabled(False)
        self._complete_btn.setEnabled(False)
        self._ai_busy(True)
        # El log se limpia al arrancar (paso funcional) y acumula funcional + técnico.
        if tipo is ManualType.FUNCIONAL:
            self._ai_log_reset(f"▶ Generando «{ctx['title']}» (funcional + técnico)…\n")
            if extracted is not None:  # diagnóstico: qué detectó el extractor
                self._ai_log_append(self._componentes_detectados(extracted))
        self._ai_log_append(f"\n━━ Manual {label.upper()} ━━")
        # Aviso honesto: una Solution con muchos componentes hace muchas llamadas.
        if n_comp > 1:
            self._ai_status.setText(
                f"Redactando manual {label} de {n_comp} componentes… "
                "(hace una llamada por componente; puede tardar varios minutos)"
            )
        else:
            self._ai_status.setText(f"Redactando manual {label}…")
        self._worker = AIWorker(call)
        self._worker.progress.connect(self._on_gen_progress)
        if tipo is ManualType.FUNCIONAL:
            self._worker.finished_ok.connect(self._on_import_func_done)
        else:
            self._worker.finished_ok.connect(self._on_import_tec_done)
        self._worker.failed.connect(self._on_import_error)
        self._worker.start()

    @staticmethod
    def _componentes_detectados(extracted) -> str:
        """Resumen claro de QUÉ encontró el extractor en el paquete (diagnóstico).
        Si algo quedó en 0, el usuario ve al toque que la extracción no lo reconoció."""
        from collections import Counter

        _ETIQUETAS = {
            "power-automate-flow": "flujo(s) de Power Automate",
            "power-apps-canvas": "app(s) de Power Apps",
            "dataverse-table": "tabla(s) de Dataverse",
            "dataverse-security": "esquema(s) de seguridad",
        }
        counts = Counter(c.kind for c in extracted.components)
        if not counts:
            return "📦 Detecté el paquete pero SIN componentes legibles."
        detalle = ", ".join(
            f"{n} {_ETIQUETAS.get(kind, kind)}" for kind, n in counts.items()
        )
        aviso = ""
        if extracted.warnings:
            aviso = "\n⚠ Avisos de extracción:\n- " + "\n- ".join(extracted.warnings)
        return f"📦 El extractor detectó: {detalle}.{aviso}\n"

    def _on_gen_progress(self, message: str) -> None:
        """Avance parcial de la generación. El mensaje completo (puede traer la
        sección recién redactada) va al panel de actividad; el status, solo la
        primera línea, corta."""
        self._ai_log_append(message)
        primera = message.splitlines()[0] if message else ""
        self._ai_status.setText(f"⏳ {primera[:90]}")
        self.statusBar().showMessage(primera[:120])

    def _import_target_id(self, tipo: ManualType, markdown: str) -> int:
        """Destino del borrador: si es ACTUALIZACIÓN, el manual existente (le
        agregás versión al guardar); si no, uno nuevo. Devuelve el manual_id."""
        ctx = self._import_ctx
        update_id = ctx["update_func_id"] if tipo is ManualType.FUNCIONAL else ctx["update_tec_id"]
        if update_id is not None:
            self._drafts[update_id] = markdown
            return update_id
        suffix = "Funcional" if tipo is ManualType.FUNCIONAL else "Técnico"
        m = self._svc.create_manual(f"{ctx['title']} ({suffix})", tipo, ctx["categoria"])
        self._drafts[m.id] = markdown
        return m.id

    def _on_import_func_done(self, markdown: str) -> None:
        self._import_func_id = self._import_target_id(ManualType.FUNCIONAL, markdown)
        self._ai_log_append(f"\n{markdown}\n")  # resultado del funcional, visible en vivo
        self.statusBar().showMessage("✓ Funcional generado. Ahora el técnico…", 6000)
        self._start_import_step(ManualType.TECNICO)  # encadena el 2º paso

    def _on_import_tec_done(self, markdown: str) -> None:
        ctx = self._import_ctx
        self._import_tec_id = self._import_target_id(ManualType.TECNICO, markdown)
        self._ai_log_append(f"\n{markdown}\n\n✓ Listo: 2 borradores generados.")
        # El snapshot (seguimiento de cambios) es SOLO para paquetes: un tema escrito
        # no tiene estructura ni versión contra la cual comparar.
        if ctx["source"] == "package":
            self._svc.save_snapshot(
                ctx["extracted"],
                manual_func_id=self._import_func_id, manual_tec_id=self._import_tec_id,
            )
        es_update = ctx["diff"] is not None
        self._ai_busy(False)
        self._ai_btn.setEnabled(True)
        self._import_btn.setEnabled(self._svc.extractor_ready)
        self._complete_btn.setEnabled(self._svc.ai_ready)
        self._refresh_manual_list(select_id=self._import_func_id)  # abre el funcional
        self._tabs.setCurrentIndex(0)  # volvemos al Editor para revisar/guardar
        self._ai_status.setText("✓ Listo.")
        msg = (
            "✓ Manuales actualizados como nueva versión (cambios marcados). Revisá y guardá cada uno."
            if es_update
            else "✓ 2 borradores generados (funcional + técnico). Revisá y guardá cada uno."
        )
        self.statusBar().showMessage(msg, 10000)

    def _on_import_error(self, message: str) -> None:
        """Si el 1º (funcional) ya se creó, NO se pierde: avisamos qué falló."""
        self._ai_busy(False)
        self._ai_btn.setEnabled(True)
        self._import_btn.setEnabled(self._svc.extractor_ready)
        self._complete_btn.setEnabled(self._svc.ai_ready)
        self._ai_status.setText("")
        if self._import_func_id is not None:
            self._refresh_manual_list(select_id=self._import_func_id)
            QMessageBox.warning(
                self, "Importación parcial",
                "El manual FUNCIONAL se generó OK, pero el TÉCNICO falló:\n\n"
                f"{message}\n\nRevisá y guardá el funcional. Para el técnico, "
                "reintentá la importación (probá con un modelo obrero si es muy grande).",
            )
        else:
            QMessageBox.critical(self, "Error de IA", message)

    def _on_ai_done(self, markdown: str) -> None:
        self._ai_busy(False)
        if self._ai_replace_editor:
            # Complementar: el resultado YA integra lo anterior → reemplaza.
            self._editor.setPlainText(markdown)
        else:
            # Resto de modos: si ya hay contenido, lo agregamos abajo sin pisarlo.
            current = self._editor.toPlainText().strip()
            self._editor.setPlainText(f"{current}\n\n{markdown}" if current else markdown)
        self._ai_status.setText("✓ Listo. Revisalo y guardá la versión.")
        self._ai_btn.setEnabled(True)
        self._import_btn.setEnabled(self._svc.extractor_ready)

    def _on_ai_error(self, message: str) -> None:
        self._ai_busy(False)
        self._ai_status.setText("")
        self._ai_btn.setEnabled(True)
        self._import_btn.setEnabled(self._svc.extractor_ready)
        self._complete_btn.setEnabled(self._svc.ai_ready)
        QMessageBox.critical(self, "Error de IA", message)

    # --- Completar pendientes [COMPLETAR] ---------------------------------

    def _on_complete_pending(self) -> None:
        if not self._current:
            QMessageBox.information(self, "Completar", "Seleccioná un manual primero.")
            return
        if not self._svc.ai_ready:
            QMessageBox.warning(self, "Completar", "Configurá la IA primero.")
            return

        base = self._editor.toPlainText().strip()
        slots = self._svc.pending_slots(base)
        if not slots:
            QMessageBox.information(
                self, "Completar",
                "No hay huecos [COMPLETAR] en el manual. ¡Está completo!",
            )
            return

        # Guardamos el estado para el callback (el worker solo trae las preguntas).
        self._pending_base = base
        self._pending_count = len(slots)

        self._ai_btn.setEnabled(False)
        self._import_btn.setEnabled(False)
        self._complete_btn.setEnabled(False)
        self._ai_busy(True)
        self._ai_status.setText(f"Buscando qué falta… ({len(slots)} pendiente/s)")
        # La IA formula las preguntas (red) → worker. El relleno es por código.
        self._worker = AIWorker(lambda: "\n".join(self._svc.ai_questions_for_pending(base)))
        self._worker.finished_ok.connect(self._on_questions_ready)
        self._worker.failed.connect(self._on_ai_error)
        self._worker.start()

    def _on_questions_ready(self, raw: str) -> None:
        self._ai_busy(False)
        self._ai_btn.setEnabled(True)
        self._import_btn.setEnabled(self._svc.extractor_ready)
        self._complete_btn.setEnabled(self._svc.ai_ready)
        self._ai_status.setText("")

        # Forzamos exactamente una pregunta por hueco (mapeo pregunta[i] ↔ hueco[i]).
        questions = [q for q in raw.split("\n") if q.strip()]
        n = self._pending_count
        questions = questions[:n] + ["Completá este dato faltante:"] * (n - len(questions))

        dlg = PendingDialog(self, questions=questions)
        if not dlg.exec():
            return
        filled = self._svc.fill_pending(self._pending_base, dlg.answers())
        self._editor.setPlainText(filled)
        self._ai_status.setText("✓ Pendientes completados. Revisá y guardá la versión.")
