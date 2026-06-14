"""Tema visual de la app (QSS), alineado con la marca del PDF.

Misma paleta que templates/style.css: la app se ve como el producto que genera.
Un solo lugar para todo el look — botones, inputs, tabs, listas, menús. Se aplica
con app.setStyleSheet(STYLESHEET) en el composition root.
"""
from __future__ import annotations

# --- Paleta de marca (idéntica a la del PDF) ---
NAVY = "#15192C"          # institucional — barras, títulos
ACCENT = "#2F71E5"        # azul acento — botones, selección
ACCENT_DEEP = "#103981"   # azul fuerte — hover/énfasis
BASE = "#ECEFF1"          # gris claro — fondos suaves
TEXT = "#263238"          # cuerpo
MUTED = "#637D8D"         # metadatos
RED = "#D74028"           # alertas

BG = "#F4F6F9"            # fondo de la app
SURFACE = "#FFFFFF"       # superficies (inputs, tarjetas)
BORDER = "#D6DCE3"        # bordes suaves
HOVER = "#F0F4FA"         # hover claro

STYLESHEET = f"""
QMainWindow, QDialog {{ background: {BG}; }}
QWidget {{ color: {TEXT}; font-family: "Segoe UI", Arial, sans-serif; font-size: 10pt; }}

/* Título del manual */
QLabel#titleLabel {{ font-size: 17pt; font-weight: 700; color: {NAVY}; }}
QLabel#sidebarHeader {{ font-size: 11pt; font-weight: 700; color: {NAVY}; }}

/* Barra de menú */
QMenuBar {{ background: {NAVY}; color: #FFFFFF; padding: 2px; }}
QMenuBar::item {{ background: transparent; padding: 6px 12px; border-radius: 4px; }}
QMenuBar::item:selected {{ background: rgba(255,255,255,0.16); }}
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 7px 24px; border-radius: 4px; }}
QMenu::item:selected {{ background: {BASE}; color: {ACCENT_DEEP}; }}

/* Botones */
QPushButton {{
  background: {ACCENT}; color: #FFFFFF; border: none;
  border-radius: 6px; padding: 7px 14px; font-weight: 600;
}}
QPushButton:hover {{ background: {ACCENT_DEEP}; }}
QPushButton:pressed {{ background: #0d2f6b; }}
QPushButton:disabled {{ background: #C4CDD6; color: #8A97A3; }}

/* Inputs */
QLineEdit, QPlainTextEdit, QComboBox, QDateEdit {{
  background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px;
  padding: 6px 8px; selection-background-color: {ACCENT}; selection-color: #FFFFFF;
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QDateEdit:focus {{
  border: 1px solid {ACCENT};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
  background: {SURFACE}; border: 1px solid {BORDER}; outline: none;
  selection-background-color: {BASE}; selection-color: {ACCENT_DEEP};
}}

/* Listas */
QListWidget {{
  background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; padding: 4px;
}}
QListWidget::item {{ padding: 8px 10px; border-radius: 6px; }}
QListWidget::item:hover {{ background: {HOVER}; }}
QListWidget::item:selected {{ background: {ACCENT}; color: #FFFFFF; }}

/* Pestañas */
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 8px; background: {SURFACE}; }}
QTabBar::tab {{
  background: transparent; color: {MUTED}; padding: 8px 16px; margin-right: 4px;
  border-bottom: 2px solid transparent; font-weight: 600;
}}
QTabBar::tab:selected {{ color: {ACCENT_DEEP}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {NAVY}; }}

/* Caja de IA y agrupadores */
QGroupBox {{
  border: 1px solid {BORDER}; border-radius: 8px; margin-top: 14px;
  background: {SURFACE}; font-weight: 600;
}}
QGroupBox::title {{
  subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {NAVY};
}}

QLabel {{ background: transparent; }}

/* Scrollbars sutiles */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #C4CDD6; border-radius: 5px; min-height: 26px; }}
QScrollBar::handle:vertical:hover {{ background: #9AA7B3; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #C4CDD6; border-radius: 5px; min-width: 26px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* Tooltips */
QToolTip {{ background: {NAVY}; color: #FFFFFF; border: none; padding: 6px 8px; }}

/* Splitter */
QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
"""
