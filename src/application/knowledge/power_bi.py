"""Conocimiento de dominio: informes de Power BI (modelo de datos y reporte)."""

_MODEL = (
    "Estás documentando el MODELO DE DATOS de un informe de Power BI. Cubrí:\n"
    "- Cada TABLA: qué representa (negocio) y su ORIGEN (la consulta M dice de dónde "
    "sale: Excel/SharePoint/SQL/web). Explicá la ruta y cómo se actualiza.\n"
    "- Las MEDIDAS DAX: qué CALCULA cada una EN TÉRMINOS DE NEGOCIO (no repitas el "
    "DAX, interpretalo), su formato y su carpeta de visualización.\n"
    "- COLUMNAS calculadas (DAX) y columnas clave; el grano de cada tabla.\n"
    "- RELACIONES: qué tablas se vinculan, por qué columnas, cardinalidad y dirección "
    "del filtro; qué permite cruzar.\n"
    "Lo que no esté en el modelo extraído, [COMPLETAR]."
)

_REPORT = (
    "Estás documentando el REPORTE (las páginas visuales) de un informe de Power BI. "
    "Cubrí:\n"
    "- Cada PÁGINA: qué pregunta de negocio responde y a quién está dirigida.\n"
    "- Los VISUALES clave: qué muestra cada uno y qué campos/medidas usa (el tipo "
    "—tarjeta, gráfico, tabla, matriz— ya viene en la estructura).\n"
    "- Las SEGMENTACIONES (slicers) y filtros: cómo el usuario acota la información.\n"
    "- Cómo LEER el tablero y navegarlo para tomar decisiones.\n"
    "Lo que no esté en el reporte extraído, [COMPLETAR]."
)

GUIDANCE = {"power-bi-model": _MODEL, "power-bi-report": _REPORT}
