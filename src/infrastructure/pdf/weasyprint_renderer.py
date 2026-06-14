"""Adaptador de PDF con WeasyPrint (HTML/CSS -> PDF).

Implementa el puerto PDFRenderer. Si algún día WeasyPrint te molesta,
escribís otro adaptador (ej: QtPdfRenderer) y cambiás UNA línea en main.py.
El resto de la app no se entera.

OJO Windows: necesita GTK/Pango instalado aparte.
  winget install --id tschoonj.GTKForWindows -e
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ...domain.entities import Manual, ManualType, ManualVersion
from ...domain.ports import PDFRenderer

_TEMPLATES_DIR = Path(__file__).parent / "templates"

# Marca que aparece en la portada del PDF. Cambialo acá si rebrandeás.
BRAND = "Mi Empresa"

_TIPO_LABEL = {ManualType.FUNCIONAL: "Manual Funcional", ManualType.TECNICO: "Manual Técnico"}


class WeasyPrintRenderer(PDFRenderer):
    def __init__(self) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(_TEMPLATES_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
        )
        self._css_path = _TEMPLATES_DIR / "style.css"

    def render(self, manual: Manual, version: ManualVersion) -> bytes:
        # Import perezoso: así importar este módulo NO falla si falta GTK.
        # Solo explota (con mensaje claro) cuando realmente generás un PDF.
        from weasyprint import CSS, HTML
        from weasyprint.text.fonts import FontConfiguration

        # OBLIGATORIO para que @font-face funcione: sin FontConfiguration,
        # WeasyPrint ignora las fuentes embebidas EN SILENCIO y usa fallbacks.
        font_config = FontConfiguration()

        template = self._env.get_template("manual.html.j2")
        html_str = template.render(
            manual=manual,
            version=version,
            body_html=version.content_html,
            tipo_label=_TIPO_LABEL[manual.type],
            categoria_label=manual.category,
            brand=BRAND,
            fecha=version.created_at.strftime("%d/%m/%Y"),
        )
        css = CSS(filename=str(self._css_path), font_config=font_config)
        document = HTML(string=html_str).render(stylesheets=[css], font_config=font_config)
        return document.write_pdf()
