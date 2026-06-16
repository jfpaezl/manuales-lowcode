"""Conocimiento de dominio: Dataverse (tablas, seguridad, configuración).

Lo más importante del crecimiento de la doc: que una tabla de Dataverse quede
documentada con sus columnas, claves, relaciones, PERMISOS y configuración —no
una descripción vaga."""

_TABLE = (
    "Estás documentando una TABLA (entidad) de Dataverse. Un buen manual de una "
    "tabla DEBE cubrir, con datos concretos extraídos (no inventes lo que no esté):\n"
    "- Identidad: nombre lógico (schema name) y nombre para mostrar; tipo de "
    "propiedad (de usuario/equipo u organización).\n"
    "- COLUMNAS en una TABLA Markdown con: nombre para mostrar | nombre lógico | "
    "tipo de dato | requerido (sí/no) | descripción. No omitas columnas.\n"
    "- Clave primaria y, si las hay, CLAVES ALTERNATIVAS (alternate keys).\n"
    "- RELACIONES con otras tablas: 1:N, N:1 y N:N, indicando la tabla relacionada "
    "y el comportamiento (cascada/restrict) cuando se sepa.\n"
    "- Reglas de negocio, validaciones y columnas calculadas/rollup si existen.\n"
    "- CONFIGURACIÓN relevante: auditoría, duplicados, seguimiento de actividades.\n"
    "Lo que no esté en la estructura extraída, marcalo con [COMPLETAR]; no lo "
    "rellenes a ojo."
)

_SECURITY = (
    "Estás documentando la SEGURIDAD/PERMISOS de Dataverse. Cubrí:\n"
    "- Cada ROL de seguridad y, por tabla, los privilegios "
    "(Crear, Leer, Escribir, Eliminar, Anexar, Anexar a, Asignar, Compartir) con "
    "su NIVEL de acceso (Ninguno, Usuario, Unidad de negocio, Principal, "
    "Organización), en TABLA.\n"
    "- Seguridad a nivel de columna (field-level security) si aplica.\n"
    "- Equipos y unidades de negocio involucradas, si están en la estructura.\n"
    "El permiso es información sensible: documentá EXACTAMENTE lo extraído; lo que "
    "no esté, [COMPLETAR]."
)

GUIDANCE = {
    "dataverse-table": _TABLE,
    "dataverse-security": _SECURITY,
}
