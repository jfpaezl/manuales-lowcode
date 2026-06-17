"""Adaptador de Word (.docx) con python-docx (Markdown -> Word nativo).

Implementa el puerto DocxRenderer. A diferencia del PDF (WeasyPrint + GTK), esto
es PURA Python: no necesita Office ni librerías de sistema, así que el "Exportar
a Word" anda en cualquier Windows sin instalar nada extra.

Construimos el documento desde el `source_markdown` ORIGINAL de cada sección (no
desde el HTML), para mapear a estilos NATIVOS de Word: los `#` van a Heading 1/2/3
(navegables y con TOC), las listas a List Bullet/Number, el código a monospace, las
tablas a tablas de Word. Así el manual queda editable de verdad, no un HTML aplastado.

Import perezoso de `docx`: importar este módulo NO falla si python-docx no está;
solo explota (con mensaje claro) cuando realmente exportás.
"""
from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

from ...domain.entities import Manual, ManualType, ManualVersion
from ...domain.ports import DocxRenderer

_DEFAULT_BRAND = "Mi Empresa"
_TIPO_LABEL = {ManualType.FUNCIONAL: "Manual Funcional", ManualType.TECNICO: "Manual Técnico"}

# Inline: **negrita**, `código`, *itálica* / _itálica_. El orden importa (negrita
# antes que itálica) y los grupos van capturados para que re.split conserve los tokens.
_INLINE = re.compile(r"(\*\*.+?\*\*|`[^`]+`|\*[^*]+\*|_[^_]+_)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_NUMBER = re.compile(r"^(\s*)\d+[.)]\s+(.*)$")
_FENCE = re.compile(r"^```")
_TAGS = re.compile(r"<[^>]+>")


class PythonDocxRenderer(DocxRenderer):
    def __init__(self, brand: str = "", tagline: str = "", logo_path: str = "") -> None:
        self.set_identity(brand, tagline, logo_path)

    def set_identity(self, brand: str = "", tagline: str = "", logo_path: str = "") -> None:
        """Cambia la identidad de marca del Word sin reiniciar la app (igual que el PDF)."""
        self._brand = brand.strip() or _DEFAULT_BRAND
        self._tagline = tagline.strip()
        self._logo_path = logo_path.strip()

    def render(self, manual: Manual, version: ManualVersion) -> bytes:
        from docx import Document  # import perezoso: no exige python-docx hasta exportar

        doc = Document()
        self._cover(doc, manual, version)
        for s in sorted(version.sections, key=lambda x: x.order):
            if s.title.strip():
                doc.add_heading(s.title.strip(), level=1)
            md = s.source_markdown or _TAGS.sub("", s.content_html or "")
            self._render_markdown(doc, md)

        buf = BytesIO()
        doc.save(buf)
        return buf.getvalue()

    # --- Portada ----------------------------------------------------------

    def _cover(self, doc, manual: Manual, version: ManualVersion) -> None:
        from docx.shared import Inches, Pt

        if self._logo_path and Path(self._logo_path).is_file():
            try:
                doc.add_picture(self._logo_path, width=Inches(1.6))
            except Exception:  # noqa: BLE001 — imagen ilegible: la portada sigue sin logo
                pass

        marca = doc.add_paragraph()
        run = marca.add_run(self._brand)
        run.bold = True
        run.font.size = Pt(16)
        if self._tagline:
            doc.add_paragraph(self._tagline)

        doc.add_heading(manual.title, level=0)
        fecha = version.created_at.strftime("%d/%m/%Y")
        sub = f"{_TIPO_LABEL[manual.type]}  ·  {manual.category}  ·  {fecha}"
        doc.add_paragraph(sub)
        doc.add_page_break()

    # --- Markdown -> Word -------------------------------------------------

    def _render_markdown(self, doc, md: str) -> None:
        lines = md.splitlines()
        i = 0
        n = len(lines)
        while i < n:
            line = lines[i]

            if _FENCE.match(line.strip()):  # bloque de código ``` ... ```
                i = self._emit_code(doc, lines, i)
                continue

            if self._is_table_row(line) and i + 1 < n and self._is_table_sep(lines[i + 1]):
                i = self._emit_table(doc, lines, i)
                continue

            stripped = line.strip()
            if not stripped:
                i += 1
                continue

            m = _HEADING.match(stripped)
            if m:
                nivel = min(len(m.group(1)), 4)
                self._heading_with_inline(doc, m.group(2).strip(), nivel)
                i += 1
                continue

            mb = _BULLET.match(line)
            mn = _NUMBER.match(line)
            if mb or mn:
                indent = len((mb or mn).group(1))
                texto = (mb or mn).group(2).strip()
                estilo = self._list_style("List Bullet" if mb else "List Number", indent)
                self._add_inline(doc.add_paragraph(style=estilo), texto)
                i += 1
                continue

            # Párrafo normal: junta líneas hasta una vacía o un bloque nuevo.
            buff = [stripped]
            j = i + 1
            while j < n and lines[j].strip() and not self._starts_block(lines[j]):
                buff.append(lines[j].strip())
                j += 1
            self._add_inline(doc.add_paragraph(), " ".join(buff))
            i = j

    @staticmethod
    def _starts_block(line: str) -> bool:
        s = line.strip()
        return bool(
            _FENCE.match(s) or _HEADING.match(s) or _BULLET.match(line) or _NUMBER.match(line)
        )

    def _emit_code(self, doc, lines: list[str], i: int) -> int:
        from docx.shared import Pt, RGBColor

        n = len(lines)
        j = i + 1
        code: list[str] = []
        while j < n and not _FENCE.match(lines[j].strip()):
            code.append(lines[j])
            j += 1
        p = doc.add_paragraph()
        self._shade(p, "F2F2F2")
        for k, cl in enumerate(code):
            run = p.add_run(cl)
            run.font.name = "Consolas"
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(0x1A, 0x1A, 0x1A)
            if k < len(code) - 1:
                run.add_break()
        return j + 1  # saltar el ``` de cierre

    def _emit_table(self, doc, lines: list[str], i: int) -> int:
        n = len(lines)
        header = self._row_cells(lines[i])
        j = i + 2  # saltar header + separador
        rows: list[list[str]] = []
        while j < n and self._is_table_row(lines[j]):
            rows.append(self._row_cells(lines[j]))
            j += 1

        cols = len(header)
        table = doc.add_table(rows=1, cols=cols)
        try:
            table.style = "Light Grid Accent 1"
        except KeyError:  # estilo no disponible: tabla sin estilo, igual válida
            pass
        for c, text in enumerate(header):
            self._add_inline(table.rows[0].cells[c].paragraphs[0], text, bold=True)
        for r in rows:
            cells = table.add_row().cells
            for c in range(cols):
                texto = r[c] if c < len(r) else ""
                self._add_inline(cells[c].paragraphs[0], texto)
        return j

    # --- Helpers de tabla -------------------------------------------------

    @staticmethod
    def _is_table_row(line: str) -> bool:
        return "|" in line and line.strip().startswith("|")

    @staticmethod
    def _is_table_sep(line: str) -> bool:
        return bool(re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", line)) and "-" in line

    @staticmethod
    def _row_cells(line: str) -> list[str]:
        return [c.strip() for c in line.strip().strip("|").split("|")]

    # --- Inline + estilos -------------------------------------------------

    def _heading_with_inline(self, doc, text: str, nivel: int) -> None:
        h = doc.add_heading("", level=nivel)
        self._add_inline(h, text)

    def _add_inline(self, paragraph, text: str, *, bold: bool = False) -> None:
        for tok in _INLINE.split(text):
            if not tok:
                continue
            if tok.startswith("**") and tok.endswith("**"):
                run = paragraph.add_run(tok[2:-2])
                run.bold = True
            elif tok.startswith("`") and tok.endswith("`"):
                run = paragraph.add_run(tok[1:-1])
                run.font.name = "Consolas"
            elif (tok.startswith("*") and tok.endswith("*")) or (
                tok.startswith("_") and tok.endswith("_")
            ):
                run = paragraph.add_run(tok[1:-1])
                run.italic = True
            else:
                run = paragraph.add_run(tok)
            if bold:
                run.bold = True

    @staticmethod
    def _list_style(base: str, indent: int) -> str:
        nivel = min(indent // 2, 2)  # 2 espacios por nivel; Word ofrece hasta 3
        return base if nivel == 0 else f"{base} {nivel + 1}"

    @staticmethod
    def _shade(paragraph, hex_color: str) -> None:
        """Fondo gris claro para los bloques de código (vía XML, python-docx no lo
        expone directo). Si algo falla, el código va sin fondo: no es crítico."""
        try:
            from docx.oxml import OxmlElement
            from docx.oxml.ns import qn

            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:fill"), hex_color)
            paragraph.paragraph_format.element.get_or_add_pPr().append(shd)
        except Exception:  # noqa: BLE001
            pass
