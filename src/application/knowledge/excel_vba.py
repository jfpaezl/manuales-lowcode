"""Conocimiento de dominio: macros VBA de Excel."""

_VBA = (
    "Estás documentando una MACRO VBA de Excel. Cubrí:\n"
    "- MÓDULOS y los procedimientos (Sub/Function) de cada uno, con su propósito.\n"
    "- Parámetros de entrada y valores de retorno de cada procedimiento.\n"
    "- Rangos/hojas/libros que lee o modifica, y referencias externas.\n"
    "- Eventos que disparan la ejecución (Workbook_Open, botones, etc.).\n"
    "- Dependencias (referencias a librerías) y supuestos sobre la estructura del "
    "libro.\n"
    "Lo que no esté en el código extraído, [COMPLETAR]."
)

GUIDANCE = {"excel-vba": _VBA}
