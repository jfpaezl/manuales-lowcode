"""Constructores de prompts para los 3 modos de IA.

Separar los prompts del servicio tiene un porqué: el día que quieras
afinar cómo redacta la IA, tocás SOLO este archivo. No mezclamos
"qué le pedimos" con "cómo orquestamos".
"""
from __future__ import annotations

from ..domain.change_tracking import DiffResult
from ..domain.entities import ManualType
from .knowledge import knowledge_for, knowledge_for_category, knowledge_for_text

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


def _resolve_knowledge(*, kind: str = "", categoria_hint: str = "", content: str = "") -> str:
    """SALVAGUARDA de ruteo del knowledge pack, en cascada de fiabilidad:
    1) por `kind` (estructura extraída — lo más confiable),
    2) por CATEGORÍA (el hint elegido),
    3) por CONTENIDO (detecta la tecnología leyendo el material real).
    Devuelve la guía o "". Así, independientemente de la categoría, se rutea al
    pack que corresponde a lo que de verdad se está documentando."""
    return (
        (knowledge_for(kind) if kind else "")
        or (knowledge_for_category(categoria_hint) if categoria_hint else "")
        or knowledge_for_text(content)
    )


def _knowledge_md(guia: str, tipo: ManualType) -> str:
    """Envuelve una guía de dominio para el prompt. SOLO en el manual TÉCNICO: el
    detalle de tablas/columnas/permisos/config es su territorio. El funcional se
    mantiene breve (lo gobierna `_nivel_detalle`), sin este bloque."""
    if tipo is not ManualType.TECNICO or not guia:
        return ""
    return f"\n\nCONOCIMIENTO DE DOMINIO (cubrí estos puntos al documentar):\n{guia}"


def _knowledge_block(
    tipo: ManualType, *, kind: str = "", categoria_hint: str = "", content: str = ""
) -> str:
    """Inyecta el knowledge pack resuelto en cascada (kind → categoría → contenido)."""
    return _knowledge_md(
        _resolve_knowledge(kind=kind, categoria_hint=categoria_hint, content=content), tipo
    )


def _knowledge_block_ref(
    tipo: ManualType, *, categoria_hint: str = "", content: str = ""
) -> str:
    """Knowledge pack como REFERENCIA (para complementar): orienta qué cubre un
    buen manual de la tecnología, pero NO autoriza a inventar secciones fuera de
    lo que el usuario pidió integrar. Respeta el contrato quirúrgico del modo."""
    if tipo is not ManualType.TECNICO:
        return ""
    guia = _resolve_knowledge(categoria_hint=categoria_hint, content=content)
    if not guia:
        return ""
    return (
        "\n\nCONOCIMIENTO DE DOMINIO (úsalo SOLO como REFERENCIA de qué cubre un buen "
        "manual de esta tecnología; aplicalo a lo que te piden integrar, SIN agregar "
        "secciones que el usuario no haya indicado):\n" + guia
    )


def _nivel_detalle(tipo: ManualType) -> str:
    """Fija el NIVEL DE DETALLE según el tipo de manual.

    Separación de responsabilidades: el FUNCIONAL describe brevemente QUÉ acción
    ejecuta cada flujo/componente y para qué sirve; el paso a paso interno (orden,
    condiciones, bucles, conectores) es del TÉCNICO. Centralizado acá para que un
    builder no contradiga al propósito declarado en `_TIPO_DESC`."""
    if tipo is ManualType.FUNCIONAL:
        return (
            "NIVEL DE DETALLE (funcional): describí BREVEMENTE qué ACCIÓN ejecuta "
            "cada flujo/componente y PARA QUÉ sirve, desde la perspectiva del "
            "negocio y del usuario. NO describas el paso a paso interno, ni "
            "condiciones, bucles, expresiones o conectores: ese nivel de detalle "
            "corresponde al manual técnico."
        )
    return (
        "NIVEL DE DETALLE (técnico): explicá el paso a paso completo, manteniendo "
        "el orden de ejecución, los anidamientos (condiciones, bucles), las "
        "expresiones y los conectores."
    )


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


def _versionamiento(
    developer: str, fecha: str, *, version: str = "", change_note: str = ""
) -> str:
    """Instrucción para que la tabla de Versionamiento use datos reales.

    OJO: el «autor» del versionamiento es el DESARROLLADOR del flujo (quien lo
    programó), NO el responsable de ejecutarlo (ese va en «Datos generales»). Si
    no se aporta, queda [COMPLETAR]: hueco honesto antes que un dato equivocado.

    `version` es la versión real del paquete (ej «1.0.0.2» de una Solution), para
    que se vea a qué versión corresponde la lectura. `change_note` resume los
    cambios cuando es una actualización (si no, «Versión inicial»)."""
    autor = developer.strip() or "[COMPLETAR]"
    ver = version.strip() or "versión 1.0"
    nota = change_note.strip() or "Versión inicial"
    return (
        "\n\nIMPORTANTE — en la sección «Versionamiento», la primera fila de la tabla "
        f"debe ser EXACTAMENTE:\n{ver} | {fecha} | {autor} | {nota}\n"
        "El «autor» es el DESARROLLADOR del flujo (quien lo construyó), no el "
        "responsable de operarlo. No uses [COMPLETAR] para la fecha; usá el valor indicado."
    )


def _resumen_cambios(diff: "DiffResult") -> str:
    """Resumen corto para la fila de Versionamiento de una actualización."""
    return (
        f"Cambios v{diff.version_from}→v{diff.version_to}: "
        f"{len(diff.deprecated)} deprecado(s), {len(diff.modified)} modificado(s), "
        f"{len(diff.added)} nuevo(s)"
    )


def _change_note(diff: "DiffResult | None") -> str:
    """Nota de cambio para el Versionamiento (vacía si no hay cambios/diff)."""
    return _resumen_cambios(diff) if (diff and diff.has_changes) else ""


def _cambios(diff: "DiffResult | None") -> str:
    """Instrucciones para marcar el seguimiento de cambios respecto a la versión
    anterior: sección dedicada + marcas inline ⚠/🔄/🆕 en los componentes."""
    if diff is None or not diff.has_changes:
        return ""
    items = []
    for n in diff.deprecated:
        items.append(
            f"- ⚠ DEPRECADO: «{n}» (estaba en {diff.version_from}, ya no está en "
            f"{diff.version_to})"
        )
    for n in diff.modified:
        items.append(f"- 🔄 MODIFICADO: «{n}»")
    for n in diff.added:
        items.append(f"- 🆕 NUEVO: «{n}»")
    listado = "\n".join(items)
    return (
        "\n\nIMPORTANTE — SEGUIMIENTO DE CAMBIOS (de la versión "
        f"{diff.version_from} a la {diff.version_to}):\n"
        "Agregá, JUSTO DESPUÉS de «Datos generales», una sección «## Cambios respecto "
        "a la versión anterior» con esta lista EXACTA:\n"
        f"{listado}\n"
        "Además, marcá inline cada componente afectado en SU PROPIO encabezado: a los "
        "MODIFICADOS agregales «🔄 MODIFICADO» en el título; a los NUEVOS «🆕 NUEVO». "
        "Para cada DEPRECADO, incluí una subsección breve «### ⚠ {nombre} (DEPRECADO)» "
        "aclarando que se dejó de usar en esta versión; si no se sabe el motivo, dejá "
        "[COMPLETAR] — no lo inventes."
    )


def build_generate(
    *, topic: str, tipo: ManualType, categoria_hint: str, author: str = "", fecha: str = "",
    context: str = "", area: str = "", developer: str = "",
) -> tuple[str, str]:
    """Modo 1: generar el manual desde cero a partir de un tema."""
    extra = f"\n\nContexto adicional aportado por el usuario:\n{context}" if context.strip() else ""
    user = (
        f"Generá {_TIPO_DESC[tipo]}\n\n"
        f"Tema/objeto a documentar: {topic}\n"
        f"Tecnología: {categoria_hint}.{extra}"
        f"{_knowledge_block(tipo, categoria_hint=categoria_hint, content=f'{topic} {context}')}\n\n"
        f"{_ESTRUCTURA[tipo]}"
        f"{_datos_generales(tipo, author, area, fecha)}"
        f"{_versionamiento(developer, fecha)}"
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
        f"Tecnología: {categoria_hint}."
        f"{_knowledge_block(tipo, categoria_hint=categoria_hint, content=f'{language_hint} {code}')}\n\n"
        "Explicá qué hace, cómo funciona, sus parámetros/entradas y salidas, "
        "y cómo usarlo. Incluí el código relevante en bloques.\n\n"
        f"```\n{code}\n```"
    )
    return _system_for(tipo), user


def build_from_package(
    *, package_name: str, package_summary: str, tipo: ManualType, categoria_hint: str,
    author: str = "", fecha: str = "", area: str = "", developer: str = "",
    version: str = "", diff: DiffResult | None = None, kind: str = "",
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
        f"{_nivel_detalle(tipo)} Si algo no está en la estructura, marcalo con "
        "[COMPLETAR]; no lo rellenes a ojo."
        f"{_knowledge_block(tipo, kind=kind, categoria_hint=categoria_hint, content=package_summary)}\n\n"
        f"{_ESTRUCTURA[tipo]}"
        f"{_datos_generales(tipo, author, area, fecha)}"
        f"{_cambios(diff)}"
        f"{_versionamiento(developer, fecha, version=version, change_note=_change_note(diff))}\n\n"
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
        f"Tecnología: {categoria_hint}."
        f"{_knowledge_block_ref(tipo, categoria_hint=categoria_hint, content=f'{current_markdown} {instructions}')}\n\n"
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
    "dataverse-table": "tabla de Dataverse",
    "dataverse-security": "esquema de seguridad de Dataverse",
}


def build_worker_section(component, tipo: ManualType, categoria_hint: str) -> tuple[str, str]:
    """OBRERO (modelo chico): documenta UN componente como una sección, no el
    manual completo. Tarea acotada y barata."""
    etiqueta = _KIND_LABEL.get(component.kind, "componente")
    user = (
        f"Documentá el siguiente {etiqueta} llamado «{component.name}», como UNA SECCIÓN "
        f"de un manual {_TIPO_DESC[tipo]}. Tecnología: {categoria_hint}.\n"
        f"IMPORTANTE: este componente ES un {etiqueta}. Respetá ESE tipo: NO lo "
        "reclasifiques (un flujo no es una tabla ni una app). Documentalo según lo que es.\n"
        "Redactá SOLO esta sección (no un manual entero, sin portada ni datos generales). "
        "Empezá con un encabezado de nivel 2 (## ) con el nombre del componente. "
        f"{_nivel_detalle(tipo)} No inventes pasos; lo que falte, [COMPLETAR]."
        f"{_knowledge_block(tipo, kind=component.kind, content=component.summary_markdown)}\n\n"
        f"Estructura extraída:\n\"\"\"\n{component.summary_markdown}\n\"\"\""
    )
    return _system_for(tipo), user


# Estructura para manuales de SOLUTION (multi-componente). A diferencia de
# _ESTRUCTURA (pensada para UN tema), esta es ORIENTADA A COMPONENTES: cada
# componente se documenta UNA vez y a fondo bajo «Componentes de la solución», y
# las demás secciones miran el conjunto. Así no se dispersa ni se adelgaza el
# contenido (que es lo que pasaba al meter cada componente en cada sección).
_ESTRUCTURA_SOLUCION = {
    ManualType.FUNCIONAL: (
        "Seguí EXACTAMENTE esta estructura, una sección por encabezado (##). "
        "NO numeres los encabezados.\n"
        "## Datos generales\n"
        "## Situación actual\n"
        "## Objetivo\n"
        "## Alcance\n"
        "## Componentes de la solución\n"
        "(por CADA componente de «Componentes documentados», UNA subsección ### con su "
        "nombre, describiendo BREVEMENTE qué acción ejecuta y para qué sirve)\n"
        "## Manual de usuario (paso a paso)\n"
        "## Riesgos, supuestos y restricciones\n"
        "## Recomendaciones\n"
        "## Versionamiento\n"
        "(tabla: versión | fecha | autor | cambios)"
    ),
    ManualType.TECNICO: (
        "Seguí EXACTAMENTE esta estructura, una sección por encabezado (##). "
        "NO numeres los encabezados.\n"
        "## Resumen técnico\n"
        "## Arquitectura general\n"
        "(capas, flujo de datos principal y cómo se relacionan los componentes entre sí)\n"
        "## Componentes de la solución\n"
        "(por CADA componente de «Componentes documentados», UNA subsección ### con su "
        "nombre, CONSERVANDO su documentación COMPLETA y detallada tal cual viene)\n"
        "## Dependencias transversales\n"
        "(conectores compartidos, listas de SharePoint, libros de Excel, recursos externos)\n"
        "## Configuración del entorno\n"
        "## Versionamiento\n"
        "(tabla: versión | fecha | autor | cambios)"
    ),
}


def build_orchestrate(
    *, solution_name: str, parts: list[str], tipo: ManualType, categoria_hint: str,
    author: str = "", fecha: str = "", area: str = "", developer: str = "",
    version: str = "", diff: DiffResult | None = None,
) -> tuple[str, str]:
    """ORQUESTADOR (modelo potente): ENSAMBLA las secciones ya redactadas por los
    obreros, CONSERVANDO cada una; agrega intro, arquitectura y cohesión."""
    cuerpo = "\n\n".join(f"--- Componente {i} ---\n{p}" for i, p in enumerate(parts, 1))
    user = (
        f"Estás armando un manual {_TIPO_DESC[tipo]} de la solución «{solution_name}», que "
        f"agrupa varios componentes YA documentados por separado. Tecnología: {categoria_hint}.\n\n"
        "Tu tarea es ENSAMBLAR, no reescribir. REGLA DE ORO: cada componente va como UNA "
        "SOLA subsección ### bajo «Componentes de la solución», CONSERVANDO su documentación "
        "tal cual viene (NO la resumas, NO la recortes, NO la repartas entre las otras "
        "secciones, NO la repitas en varias). Las demás secciones (resumen, arquitectura, "
        "dependencias, configuración) son TUYAS: escribilas mirando el CONJUNTO, sin volver "
        "a copiar el detalle de cada componente. Respetá el NOMBRE y el TIPO REAL de cada "
        "componente (si abajo dice «Flujo de Power Automate», es un flujo: NO lo conviertas "
        "en tabla ni en otra cosa). Lo que falte, [COMPLETAR]."
        f"{_knowledge_block(tipo, kind='power-platform-solution')}\n\n"
        f"{_ESTRUCTURA_SOLUCION[tipo]}"
        f"{_datos_generales(tipo, author, area, fecha)}"
        f"{_cambios(diff)}"
        f"{_versionamiento(developer, fecha, version=version, change_note=_change_note(diff))}\n\n"
        f"Componentes documentados:\n{cuerpo}"
    )
    return _system_for(tipo), user


def build_from_transcription(
    *, transcription: str, tipo: ManualType, categoria_hint: str, author: str = "", fecha: str = "",
    area: str = "", developer: str = "",
) -> tuple[str, str]:
    """Modo 3: convertir una transcripción hablada en un manual estructurado."""
    user = (
        "A continuación va la TRANSCRIPCIÓN de alguien explicando de forma "
        "informal cómo funciona una automatización. Convertila en "
        f"{_TIPO_DESC[tipo]} bien estructurado.\n"
        f"Tecnología: {categoria_hint}."
        f"{_knowledge_block(tipo, categoria_hint=categoria_hint, content=transcription)}\n\n"
        "Limpiá las muletillas, ordená las ideas en secciones lógicas y completá "
        "lo que falte con [COMPLETAR]. No pierdas ningún paso técnico mencionado.\n\n"
        f"{_ESTRUCTURA[tipo]}"
        f"{_datos_generales(tipo, author, area, fecha)}"
        f"{_versionamiento(developer, fecha)}\n\n"
        f"Transcripción:\n\"\"\"\n{transcription}\n\"\"\""
    )
    return _system_for(tipo), user
