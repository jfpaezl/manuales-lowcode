"""Tests del nivel de DETALLE por tipo de manual.

Regla de negocio: el manual FUNCIONAL describe BREVEMENTE qué acción ejecuta
cada flujo/componente (el QUÉ y el PARA QUÉ). El paso a paso interno —orden de
ejecución, condiciones, bucles, conectores— es responsabilidad del manual
TÉCNICO. Estos tests blindan esa separación para que no se vuelva a romper.
"""
from src.application.ai_prompts import (
    build_complement,
    build_document_code,
    build_from_package,
    build_from_transcription,
    build_generate,
    build_orchestrate,
    build_worker_section,
)
from src.domain.change_tracking import DiffResult
from src.domain.entities import ExtractedPackage, ManualType


def _comp(name: str = "Flujo X") -> ExtractedPackage:
    return ExtractedPackage(
        kind="power-automate-flow", name=name, summary_markdown=f"# {name}\n- paso"
    )


# --- Obrero (documenta cada componente de una Solution) -------------------

def test_worker_funcional_pide_descripcion_breve_no_paso_a_paso():
    _, user = build_worker_section(_comp(), ManualType.FUNCIONAL, "Power Automate")
    low = user.lower()
    assert "breve" in low                       # pide brevedad
    assert "acción" in low                       # qué ACCIÓN ejecuta
    assert "técnico" in low                       # el detalle es del técnico
    # NO debe PEDIR el detalle interno (marcador técnico ausente)
    assert "orden de ejecución" not in low


def test_worker_tecnico_si_pide_el_detalle_interno():
    _, user = build_worker_section(_comp(), ManualType.TECNICO, "Power Automate")
    low = user.lower()
    assert "orden de ejecución" in low
    assert "anidamientos" in low


# --- Flujo suelto (build_from_package atómico) ----------------------------

def test_from_package_funcional_no_pide_anidamientos():
    _, user = build_from_package(
        package_name="F", package_summary="# F\n- paso",
        tipo=ManualType.FUNCIONAL, categoria_hint="Power Automate",
    )
    low = user.lower()
    assert "breve" in low
    assert "anidamientos" not in low


def test_from_package_tecnico_si_pide_anidamientos():
    _, user = build_from_package(
        package_name="F", package_summary="# F\n- paso",
        tipo=ManualType.TECNICO, categoria_hint="Power Automate",
    )
    assert "anidamientos" in user.lower()


# --- Orquestador (Solution): misma estructura canónica que el resto --------

def _orchestrate_funcional() -> str:
    _, user = build_orchestrate(
        solution_name="MiSolución", parts=["## Comp1\nx", "## Comp2\ny"],
        tipo=ManualType.FUNCIONAL, categoria_hint="Power Platform",
        author="Ana", area="RRHH", fecha="01/01/2030",
    )
    return user


def test_orchestrate_funcional_usa_la_estructura_canonica():
    user = _orchestrate_funcional()
    # Mismas secciones canónicas que un funcional de flujo/macro
    assert "## Datos generales" in user
    assert "## Situación actual" in user
    assert "## Versionamiento" in user


def test_orchestrate_versionamiento_va_siempre_al_final():
    user = _orchestrate_funcional()
    # Recomendaciones (penúltima) antes de Versionamiento (última)
    assert user.index("## Recomendaciones") < user.index("## Versionamiento")


def test_orchestrate_integra_componentes_como_subsecciones():
    user = _orchestrate_funcional()
    # Los componentes NO van como ## sueltos: van como ### dentro de las canónicas
    assert "###" in user


def test_orchestrate_tecnico_estructura_orientada_a_componentes():
    _, user = build_orchestrate(
        solution_name="S", parts=["## C\nx"], tipo=ManualType.TECNICO,
        categoria_hint="Power Platform",
    )
    # Estructura de SOLUTION: cada componente UNA vez bajo «Componentes de la solución».
    assert "## Componentes de la solución" in user
    assert "## Versionamiento" in user
    # Regla anti-dispersión: conservar, no repartir ni repetir.
    low = user.lower()
    assert "conservando" in low or "conservá" in low
    assert "no la repitas" in low or "no la repartas" in low


# --- Responsable (ejecuta) ≠ Desarrollador (programa) ---------------------

def test_responsable_va_a_datos_generales_y_desarrollador_a_versionamiento():
    _, user = build_generate(
        topic="x", tipo=ManualType.FUNCIONAL, categoria_hint="Power Apps",
        author="Ana Responsable", area="Finanzas", fecha="01/01/2030",
        developer="Beto Desarrollador",
    )
    # Datos generales → Responsable (quien ejecuta)
    assert "Responsable | Ana Responsable" in user
    # Versionamiento → el Autor de la v1.0 es el DESARROLLADOR, no el responsable
    assert "versión 1.0 | 01/01/2030 | Beto Desarrollador | Versión inicial" in user
    # el responsable NO se cuela como autor del versionamiento
    assert "01/01/2030 | Ana Responsable" not in user


def test_versionamiento_sin_desarrollador_queda_completar():
    _, user = build_generate(
        topic="x", tipo=ManualType.FUNCIONAL, categoria_hint="Power Apps",
        author="Ana Responsable", area="Finanzas", fecha="01/01/2030",
    )  # sin developer
    # El responsable sí queda en Datos generales...
    assert "Responsable | Ana Responsable" in user
    # ...pero el autor del versionamiento es un hueco honesto, no el responsable
    assert "versión 1.0 | 01/01/2030 | [COMPLETAR] | Versión inicial" in user


# --- Seguimiento de cambios (deprecación / modificación / nuevo) ----------

def _diff(deprecated=(), modified=(), added=(), vf="1.0.0.1", vt="1.0.0.2"):
    return DiffResult(
        version_from=vf, version_to=vt,
        deprecated=list(deprecated), modified=list(modified), added=list(added),
    )


def test_orchestrate_sin_diff_no_agrega_seccion_de_cambios():
    _, user = build_orchestrate(
        solution_name="S", parts=["## C\nx"], tipo=ManualType.FUNCIONAL,
        categoria_hint="Power Platform",
    )
    assert "Cambios respecto a la versión anterior" not in user


def test_orchestrate_con_diff_marca_deprecado_modificado_nuevo():
    diff = _diff(deprecated=["NotifViejo"], modified=["Solicitudes"], added=["Auditoría"])
    _, user = build_orchestrate(
        solution_name="S", parts=["## Solicitudes\nx"], tipo=ManualType.FUNCIONAL,
        categoria_hint="Power Platform", version="1.0.0.2", diff=diff,
    )
    assert "Cambios respecto a la versión anterior" in user
    assert "NotifViejo" in user and "DEPRECADO" in user
    assert "Solicitudes" in user and "MODIFICADO" in user
    assert "Auditoría" in user and "NUEVO" in user
    # Transición de versión visible
    assert "1.0.0.1" in user and "1.0.0.2" in user


def test_versionamiento_muestra_la_version_de_la_solution():
    # En la fila del versionamiento debe verse a qué versión de la Solution corresponde.
    diff = _diff(modified=["X"])
    _, user = build_orchestrate(
        solution_name="S", parts=["## X\nx"], tipo=ManualType.TECNICO,
        categoria_hint="Power Platform", version="1.0.0.2", fecha="02/02/2032",
        developer="Beto", diff=diff,
    )
    # La fila de versionamiento arranca con la versión real de la Solution, no "1.0"
    assert "1.0.0.2 | 02/02/2032 | Beto" in user


def test_from_package_atomico_acepta_diff():
    diff = _diff(modified=["MiFlujo"])
    _, user = build_from_package(
        package_name="MiFlujo", package_summary="# F", tipo=ManualType.TECNICO,
        categoria_hint="Power Automate", version="2.0", diff=diff,
    )
    assert "Cambios respecto a la versión anterior" in user
    assert "MiFlujo" in user and "MODIFICADO" in user


# --- Knowledge packs (conocimiento de dominio inyectado al prompt) --------

def test_worker_inyecta_conocimiento_de_dataverse():
    comp = ExtractedPackage(kind="dataverse-table", name="Cuentas", summary_markdown="# t")
    _, user = build_worker_section(comp, ManualType.TECNICO, "Dataverse")
    # La guía de tabla de Dataverse llega al prompt (columnas, claves, permisos...)
    low = user.lower()
    assert "columnas" in low
    assert "clave" in low or "claves" in low


def test_worker_kind_desconocido_no_rompe():
    comp = ExtractedPackage(kind="kind-inexistente", name="X", summary_markdown="# x")
    _, user = build_worker_section(comp, ManualType.FUNCIONAL, "Otro")
    assert "## " not in user[:5]  # sigue generando prompt normal
    assert user  # no explota ni queda vacío


def test_from_package_inyecta_conocimiento_por_kind():
    _, user = build_from_package(
        package_name="MiMacro", package_summary="# m", tipo=ManualType.TECNICO,
        categoria_hint="Macros", kind="excel-vba",
    )
    assert "módulos" in user.lower() or "procedimientos" in user.lower()


def test_salvaguarda_generate_detecta_por_contenido_si_la_categoria_no_ayuda():
    # Categoría genérica ("una automatización") pero el tema habla de Power Automate.
    _, user = build_generate(
        topic="documentar un flujo de Power Automate con su trigger y conectores",
        tipo=ManualType.TECNICO, categoria_hint="una automatización",
    )
    assert "trigger" in user.lower() or "conectores" in user.lower()


def test_salvaguarda_from_package_kind_desconocido_cae_a_contenido():
    # kind no reconocido pero la estructura tiene señales claras de un flujo.
    _, user = build_from_package(
        package_name="X", package_summary="acción OpenApiConnection con runAfter",
        tipo=ManualType.TECNICO, categoria_hint="Otro", kind="kind-raro",
    )
    assert "trigger" in user.lower() or "conectores" in user.lower()


# --- Knowledge por CATEGORÍA (modos sin paquete: generar/código/transcripción) ---

def test_generate_tecnico_inyecta_conocimiento_por_categoria():
    _, user = build_generate(
        topic="Aprobaciones", tipo=ManualType.TECNICO,
        categoria_hint="flujos de Power Automate",
    )
    assert "trigger" in user.lower() or "conectores" in user.lower()


def test_generate_funcional_no_inyecta_conocimiento():
    # El knowledge pack es del técnico; el funcional se mantiene breve.
    _, user = build_generate(
        topic="Aprobaciones", tipo=ManualType.FUNCIONAL,
        categoria_hint="flujos de Power Automate",
    )
    assert "CONOCIMIENTO DE DOMINIO" not in user


def test_document_code_tecnico_inyecta_conocimiento_por_categoria():
    _, user = build_document_code(
        code="Sub X()\nEnd Sub", tipo=ManualType.TECNICO, categoria_hint="macros (Excel/VBA)",
    )
    assert "módulos" in user.lower() or "procedimientos" in user.lower()


def test_transcription_tecnico_inyecta_conocimiento_por_categoria():
    _, user = build_from_transcription(
        transcription="explico la app", tipo=ManualType.TECNICO,
        categoria_hint="Power Apps (Power Platform)",
    )
    assert "pantallas" in user.lower() or "orígenes de datos" in user.lower()


def test_complement_tecnico_inyecta_conocimiento_como_referencia():
    _, user = build_complement(
        current_markdown="## Objetivo\nx", instructions="agregá la tabla de cuentas",
        tipo=ManualType.TECNICO, categoria_hint="tablas de Dataverse",
    )
    low = user.lower()
    assert "columnas" in low                         # el pack llega
    assert "referencia" in low                        # pero framed como referencia
    assert "sin agregar secciones" in low             # no rompe el contrato de complementar


def test_complement_funcional_no_inyecta_conocimiento():
    _, user = build_complement(
        current_markdown="## Objetivo\nx", instructions="algo",
        tipo=ManualType.FUNCIONAL, categoria_hint="tablas de Dataverse",
    )
    assert "CONOCIMIENTO DE DOMINIO" not in user
