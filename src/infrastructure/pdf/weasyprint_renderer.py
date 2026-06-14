"""Adaptador de PDF con WeasyPrint (HTML/CSS -> PDF).

Implementa el puerto PDFRenderer. Si algún día WeasyPrint te molesta,
escribís otro adaptador (ej: QtPdfRenderer) y cambiás UNA línea en main.py.
El resto de la app no se entera.

OJO Windows: necesita GTK/Pango instalado aparte.
  winget install --id tschoonj.GTKForWindows -e
"""
from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ...domain.entities import Manual, ManualType, ManualVersion
from ...domain.ports import PDFRenderer

_TEMPLATES_DIR = Path(__file__).parent / "templates"

# Marca por defecto si no se configuró ninguna (la identidad real se setea en la app).
_DEFAULT_BRAND = "Mi Empresa"

_TIPO_LABEL = {ManualType.FUNCIONAL: "Manual Funcional", ManualType.TECNICO: "Manual Técnico"}


class WeasyPrintRenderer(PDFRenderer):
    def __init__(self, brand: str = "", tagline: str = "", logo_path: str = "") -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(_TEMPLATES_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
        )
        self._css_path = _TEMPLATES_DIR / "style.css"
        self.set_identity(brand, tagline, logo_path)

    def set_identity(self, brand: str = "", tagline: str = "", logo_path: str = "") -> None:
        """Cambia la identidad de marca del PDF sin reiniciar la app."""
        self._brand = brand.strip() or _DEFAULT_BRAND
        self._tagline = tagline.strip()
        self._logo_path = logo_path.strip()

    def _logo_data_uri(self) -> str:
        """Convierte el logo a data URI (base64) para embeberlo en el PDF.
        Si no hay logo o el archivo no existe, devuelve "" (la portada lo omite)."""
        if not self._logo_path:
            return ""
        p = Path(self._logo_path)
        if not p.is_file():
            return ""
        mime = mimetypes.guess_type(p.name)[0] or "image/png"
        data = base64.b64encode(p.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{data}"

    def _build_html(self, manual: Manual, version: ManualVersion) -> str:
        """Arma el HTML del manual (solo Jinja, NO necesita GTK: testeable)."""
        template = self._env.get_template("manual.html.j2")
        return template.render(
            manual=manual,
            version=version,
            body_html=version.content_html,
            tipo_label=_TIPO_LABEL[manual.type],
            categoria_label=manual.category,
            brand=self._brand,
            tagline=self._tagline,
            logo_uri=self._logo_data_uri(),
            fecha=version.created_at.strftime("%d/%m/%Y"),
        )

    def render(self, manual: Manual, version: ManualVersion) -> bytes:
        # Import perezoso: así importar este módulo NO falla si falta GTK.
        # Solo explota (con mensaje claro) cuando realmente generás un PDF.
        from weasyprint import CSS, HTML
        from weasyprint.text.fonts import FontConfiguration

        # OBLIGATORIO para que @font-face funcione: sin FontConfiguration,
        # WeasyPrint ignora las fuentes embebidas EN SILENCIO y usa fallbacks.
        font_config = FontConfiguration()

        html_str = self._build_html(manual, version)
        css = CSS(filename=str(self._css_path), font_config=font_config)
        document = HTML(string=html_str).render(stylesheets=[css], font_config=font_config)
        return document.write_pdf()
