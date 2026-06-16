"""Conocimiento de dominio: flujos de Power Automate."""

_FLOW = (
    "Estás documentando un FLUJO de Power Automate. Cubrí:\n"
    "- DESENCADENADOR (trigger): qué lo dispara (automático/instantáneo/programado) "
    "y sus condiciones.\n"
    "- CONECTORES usados (ej: Office 365, SharePoint, Dataverse) y a qué sistema "
    "acceden.\n"
    "- Variables y parámetros de entrada/salida.\n"
    "- Manejo de errores: configuraciones «run after», reintentos, alcances "
    "(scopes) try/catch si existen."
)

GUIDANCE = {"power-automate-flow": _FLOW}
