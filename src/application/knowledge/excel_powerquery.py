"""Conocimiento de dominio: consultas Power Query (lenguaje M) de Excel."""

_PQ = (
    "Estás documentando CONSULTAS de Power Query (lenguaje M) de Excel. Cubrí:\n"
    "- Cada CONSULTA: su propósito y qué entrega (tabla, lista, valor).\n"
    "- ORÍGENES de datos de cada una (libro/hoja, SQL, web/API, carpeta, otra "
    "consulta) y cómo se conecta.\n"
    "- Los PASOS aplicados en orden y qué hace cada uno (filtros, columnas, "
    "cambios de tipo, merges/uniones, appends, agrupaciones, dinamizar).\n"
    "- PARÁMETROS y DEPENDENCIAS entre consultas (cuál referencia a cuál).\n"
    "- Dónde TERMINA el resultado (hoja, tabla, modelo de datos) y supuestos sobre "
    "la estructura del origen (encabezados, tipos).\n"
    "Lo que no esté en el código M extraído, [COMPLETAR]."
)

GUIDANCE = {"excel-powerquery": _PQ}
