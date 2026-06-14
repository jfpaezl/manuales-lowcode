"""Constructores de prompts para los 3 modos de IA.

Separar los prompts del servicio tiene un porqué: el día que quieras
afinar cómo redacta la IA, tocás SOLO este archivo. No mezclamos
"qué le pedimos" con "cómo orquestamos".
"""
from __future__ import annotations

from ..domain.entities import ManualType

_TIPO_DESC = {
    ManualType.FUNCIONAL: (
        "un MANUAL FUNCIONAL: enfocado en QUÉ hace la solución y CÓMO se usa "
        "desde el punto de vista del usuario final. Nada de detalles internos de código."
    ),
    ManualType.TECNICO: (
        "un MANUAL TÉCNICO: enfocado en CÓMO está construida la solución "
        "(arquitectura, lógica, dependencias, configuración) para otro desarrollador."
    ),
}

_SYSTEM_BASE = (
    "Sos un redactor técnico senior especializado en documentar automatizaciones "
    "y desarrollo low-code para un entorno corporativo. Redactás en español NEUTRO y "
    "PROFESIONAL (sin voseo ni modismos), claro, preciso y orientado al usuario. "
    "Seguís los lineamientos de documentación de usuario de software ISO/IEC/IEEE 26514: "
    "información completa, bien estructurada, mantenible y centrada en lo que el usuario "
    "necesita saber y hacer. "
    "Devolvés SIEMPRE el contenido en Markdown válido, con encabezados (##), listas, tablas y "
    "bloques de código cuando corresponda. No inventás datos: si falta información, la marcás "
    "explícitamente con [COMPLETAR]. No agregás charla ni preámbulos: solo el manual."
)

# Estructura estándar por tipo de manual (plantilla basada en ISO/IEC/IEEE 26514).
_ESTRUCTURA = {
    ManualType.FUNCIONAL: (
        "Seguí EXACTAMENTE esta estructura, una sección por cada encabezado (##).\n"
        "NO numeres los encabezados: escribilos sin número (la numeración se agrega sola).\n"
        "## Datos generales\n"
        "(nombre de la iniciativa, área, responsable, fecha y versión — en tabla)\n"
        "## Situación actual\n"
        "## Objetivo\n"
        "## Alcance\n"
        "## Requerimientos funcionales\n"
        "## Historias de usuario\n"
        "(formato: «Como <rol> quiero <acción> para <beneficio>»)\n"
        "## Criterios de aceptación\n"
        "## Manual de usuario (paso a paso)\n"
        "## Usabilidad del entregable\n"
        "## Riesgos, supuestos y restricciones\n"
        "## Recomendaciones\n"
        "## Versionamiento\n"
        "(tabla: versión | fecha | autor | cambios)"
    ),
    ManualType.TECNICO: (
        "Seguí EXACTAMENTE esta estructura, una sección por cada encabezado (##).\n"
        "NO numeres los encabezados: escribilos sin número (la numeración se agrega sola).\n"
        "## Resumen técnico\n"
        "## Arquitectura y componentes\n"
        "## Dependencias y configuración\n"
        "## Lógica y flujo de la solución\n"
        "## Detalle de implementación\n"
        "(incluí los bloques de código relevantes)\n"
        "## Manejo de errores y excepciones\n"
        "## Pruebas y validación\n"
        "## Mantenimiento y consideraciones\n"
        "## Versionamiento\n"
        "(tabla: versión | fecha | autor | cambios)"
    ),
}


def _system_for(tipo: ManualType) -> str:
    return f"{_SYSTEM_BASE}\n\nEstás escribiendo {_TIPO_DESC[tipo]}"


def _datos_generales(tipo: ManualType, author: str, area: str, fecha: str) -> str:
    """Fuerza los datos REALES en la sección «Datos generales» (solo funcional).

    Estos datos los aporta el usuario, la IA NO los inventa. Si falta alguno,
    queda [COMPLETAR]: preferimos un hueco honesto a un dato alucinado."""
    if tipo is not ManualType.FUNCIONAL:
        return ""
    responsable = author.strip() or "[COMPLETAR]"
    sector = area.strip() or "[COMPLETAR]"
    return (
        "\n\nIMPORTANTE — la estructura YA tiene UNA sección «Datos generales». "
        "NO crees una segunda ni repitas la tabla: completá esa MISMA sección. Su "
        "tabla debe incluir estas filas con EXACTAMENTE estos valores (no los "
        "inventes ni los cambies):\n"
        f"Responsable | {responsable}\n"
        f"Área | {sector}\n"
        f"Fecha | {fecha}"
    )


def _versionamiento(author: str, fecha: str) -> str:
    """Instrucción para que la tabla de Versionamiento use datos reales."""
    autor = author.strip() or "[COMPLETAR]"
    return (
        "\n\nIMPORTANTE — en la sección «Versionamiento», la primera fila de la tabla "
        f"debe ser EXACTAMENTE:\nversión 1.0 | {fecha} | {autor} | Versión inicial\n"
        "No uses [COMPLETAR] para la fecha ni para el autor: usá los valores indicados."
    )


def build_generate(
    *, topic: str, tipo: ManualType, categoria_hint: str, author: str = "", fecha: str = "",
    context: str = "", area: str = "",
) -> tuple[str, str]:
    """Modo 1: generar el manual desde cero a partir de un tema."""
    extra = f"\n\nContexto adicional aportado por el usuario:\n{context}" if context.strip() else ""
    user = (
        f"Generá {_TIPO_DESC[tipo]}\n\n"
        f"Tema/objeto a documentar: {topic}\n"
        f"Tecnología: {categoria_hint}.{extra}\n\n"
        f"{_ESTRUCTURA[tipo]}"
        f"{_datos_generales(tipo, author, area, fecha)}"
        f"{_versionamiento(author, fecha)}"
    )
    return _system_for(tipo), user


def build_questions(slots) -> tuple[str, str]:
    """Modo 6: a partir de los huecos [COMPLETAR] detectados, la IA redacta UNA
    pregunta clara por hueco para que el autor aporte el dato faltante."""
    items = "\n".join(
        f"{i}. En «{s.section or 'el documento'}»: {s.line}"
        for i, s in enumerate(slots, 1)
    )
    system = (
        "Sos un asistente que ayuda a un autor a completar un manual. Hacés "
        "preguntas claras, concretas y breves, en español neutro y profesional."
    )
    user = (
        "El manual tiene huecos marcados con [COMPLETAR]. Por CADA hueco, redactá "
        "UNA pregunta clara para que el autor aporte el dato que falta, usando el "
        "contexto de la sección. Devolvé EXACTAMENTE una pregunta por hueco, en el "
        "MISMO orden, una por línea, SIN numerar y sin ningún otro texto.\n\n"
        f"Huecos ({len(slots)}):\n{items}"
    )
    return system, user


def build_document_code(
    *, code: str, tipo: ManualType, categoria_hint: str, language_hint: str = ""
) -> tuple[str, str]:
    """Modo 2: documentar código pegado (Python/VBA/Power Fx/etc.)."""
    lang = f" (lenguaje: {language_hint})" if language_hint else ""
    user = (
        f"Documentá el siguiente código{lang} como {_TIPO_DESC[tipo]}\n"
        f"Tecnología: {categoria_hint}.\n\n"
        "Explicá qué hace, cómo funciona, sus parámetros/entradas y salidas, "
        "y cómo usarlo. Incluí el código relevante en bloques.\n\n"
        f"```\n{code}\n```"
    )
    return _system_for(tipo), user


def build_from_package(
    *, package_name: str, package_summary: str, tipo: ManualType, categoria_hint: str,
    author: str = "", fecha: str = "", area: str = "",
) -> tuple[str, str]:
    """Modo 4: generar el manual a partir de la estructura extraída de un paquete.

    package_summary es la lógica REAL extraída del ZIP (trigger, acciones, orden,
    anidamientos). Es verdad verificable: la IA la redacta, NO la inventa.
    """
    user = (
        f"A continuación va la ESTRUCTURA REAL extraída de un paquete exportado "
        f"(«{package_name}»). Es la lógica verdadera del flujo: respetala con fidelidad, "
        f"NO inventes pasos ni conectores que no estén. Convertila en "
        f"{_TIPO_DESC[tipo]} bien estructurado.\n"
        f"Tecnología: {categoria_hint}.\n\n"
        "Explicá cada paso en lenguaje claro para el lector, manteniendo el orden de "
        "ejecución y los anidamientos (condiciones, bucles). Si algo no está en la "
        "estructura, marcalo con [COMPLETAR]; no lo rellenes a ojo.\n\n"
        f"{_ESTRUCTURA[tipo]}"
        f"{_datos_generales(tipo, author, area, fecha)}"
        f"{_versionamiento(author, fecha)}\n\n"
        f"Estructura extraída:\n\"\"\"\n{package_summary}\n\"\"\""
    )
    return _system_for(tipo), user


def build_complement(
    *, current_markdown: str, instructions: str, tipo: ManualType, categoria_hint: str,
) -> tuple[str, str]:
    """Modo 5: complementar/enriquecer un manual YA redactado.

    La IA recibe el manual actual + indicaciones nuevas e INTEGRA todo en un
    único manual, sin perder lo que había ni duplicar secciones. Devuelve el
    manual COMPLETO actualizado (no un fragmento, no un segundo documento)."""
    secciones = _secciones_existentes(current_markdown)
    user = (
        "A continuación hay un MANUAL ya redactado en Markdown. Tu tarea es "
        "COMPLEMENTARLO: integrá la información/indicaciones nuevas que te doy "
        "DENTRO del manual existente, en las secciones que correspondan.\n\n"
        "Reglas:\n"
        "- NO pierdas nada de lo que ya está. NO dupliques secciones: si una sección "
        "ya existe (por ej. «Datos generales»), ACTUALIZÁ esa misma, no agregues otra.\n"
        "- Devolvé el manual COMPLETO y actualizado (no solo los cambios).\n"
        "- Mantené la estructura y el estilo. Encabezados SIN numerar (la "
        "numeración se agrega sola).\n"
        "- Español neutro y profesional. No inventes datos: lo que falte, [COMPLETAR].\n"
        f"{secciones}\n"
        f"Tecnología: {categoria_hint}.\n\n"
        f"Información / indicaciones a integrar:\n{instructions}\n\n"
        f"Manual actual:\n\"\"\"\n{current_markdown}\n\"\"\""
    )
    return _system_for(tipo), user


def _secciones_existentes(markdown: str) -> str:
    """Lista las secciones (encabezados ##) que YA tiene el manual, para anclar a
    la IA: ese es el conjunto exacto, no debe agregar ni duplicar ninguna."""
    titulos = [
        line.lstrip("#").strip()
        for line in markdown.splitlines()
        if line.strip().startswith("## ")
    ]
    if not titulos:
        return ""
    lista = "\n".join(f"  - {t}" for t in titulos)
    return (
        "- El manual tiene EXACTAMENTE estas secciones; mantené este mismo conjunto, "
        "sin agregar ni duplicar ninguna:\n" + lista
    )


_KIND_LABEL = {
    "power-automate-flow": "flujo de Power Automate",
    "power-apps-canvas": "app de Power Apps",
}


def build_worker_section(component, tipo: ManualType, categoria_hint: str) -> tuple[str, str]:
    """OBRERO (modelo chico): documenta UN componente como una sección, no el
    manual completo. Tarea acotada y barata."""
    etiqueta = _KIND_LABEL.get(component.kind, "componente")
    user = (
        f"Documentá el siguiente {etiqueta} llamado «{component.name}», como UNA SECCIÓN "
        f"de un manual {_TIPO_DESC[tipo]}. Tecnología: {categoria_hint}.\n"
        "Redactá SOLO esta sección (no un manual entero, sin portada ni datos generales). "
        "Empezá con un encabezado de nivel 2 (## ) con el nombre del componente. Explicá "
        "qué hace y cómo, con fidelidad a la estructura. No inventes pasos; lo que falte, "
        "[COMPLETAR].\n\n"
        f"Estructura extraída:\n\"\"\"\n{component.summary_markdown}\n\"\"\""
    )
    return _system_for(tipo), user


def build_orchestrate(
    *, solution_name: str, parts: list[str], tipo: ManualType, categoria_hint: str,
    author: str = "", fecha: str = "", area: str = "",
) -> tuple[str, str]:
    """ORQUESTADOR (modelo potente): integra las secciones ya redactadas por los
    obreros en UN manual coherente. Agrega introducción, orden y cohesión."""
    cuerpo = "\n\n".join(f"--- Componente {i} ---\n{p}" for i, p in enumerate(parts, 1))
    user = (
        f"Estás armando un manual {_TIPO_DESC[tipo]} de la solución «{solution_name}», que "
        f"agrupa varios componentes YA documentados por separado. Tecnología: {categoria_hint}.\n\n"
        "Tu tarea: integrarlos en UN manual coherente y bien ordenado. Agregá una "
        "introducción que explique la solución en conjunto y cómo se relacionan sus "
        "componentes. NO pierdas el contenido de cada componente; dales orden lógico y "
        "cohesión. Encabezados SIN numerar (la numeración se agrega sola)."
        f"{_datos_generales(tipo, author, area, fecha)}"
        f"{_versionamiento(author, fecha)}\n\n"
        f"Componentes documentados:\n{cuerpo}"
    )
    return _system_for(tipo), user


def build_from_transcription(
    *, transcription: str, tipo: ManualType, categoria_hint: str, author: str = "", fecha: str = "",
    area: str = "",
) -> tuple[str, str]:
    """Modo 3: convertir una transcripción hablada en un manual estructurado."""
    user = (
        "A continuación va la TRANSCRIPCIÓN de alguien explicando de forma "
        "informal cómo funciona una automatización. Convertila en "
        f"{_TIPO_DESC[tipo]} bien estructurado.\n"
        f"Tecnología: {categoria_hint}.\n\n"
        "Limpiá las muletillas, ordená las ideas en secciones lógicas y completá "
        "lo que falte con [COMPLETAR]. No pierdas ningún paso técnico mencionado.\n\n"
        f"{_ESTRUCTURA[tipo]}"
        f"{_datos_generales(tipo, author, area, fecha)}"
        f"{_versionamiento(author, fecha)}\n\n"
        f"Transcripción:\n\"\"\"\n{transcription}\n\"\"\""
    )
    return _system_for(tipo), user
