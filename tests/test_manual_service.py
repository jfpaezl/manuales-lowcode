import pytest

from src.application.manual_service import ManualService
from src.domain.entities import ExtractedPackage, ManualType, Section
from src.domain.ports import AIProvider, PackageExtractor, PDFRenderer
from src.infrastructure.category_repository import SQLiteCategoryRepository
from src.infrastructure.db import connect, init_db
from src.infrastructure.manual_repository import SQLiteManualRepository


class FakeRenderer(PDFRenderer):
    def render(self, manual, version) -> bytes:
        return f"%PDF fake {manual.title} v{version.version}".encode()


class FakeAI(AIProvider):
    def __init__(self, canned: str = "## Resultado\nTexto generado") -> None:
        self.canned = canned
        self.last_system = None
        self.last_user = None

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.last_system = system_prompt
        self.last_user = user_prompt
        return self.canned


class RecordingAI(AIProvider):
    """IA que registra cuántas veces la llamaron y con qué prompts."""
    def __init__(self, canned: str = "salida") -> None:
        self.canned = canned
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.canned


class FakeExtractor(PackageExtractor):
    def __init__(self, package: ExtractedPackage) -> None:
        self.package = package
        self.last_data = None

    def supports(self, names: list[str]) -> bool:
        return True

    def extract(self, data: bytes, filename: str = "") -> ExtractedPackage:
        self.last_data = data
        return self.package


@pytest.fixture
def service_factory():
    def make(*, ai=None, renderer=None, extractor=None, worker_ai=None):
        conn = connect(":memory:")
        init_db(conn)
        repo = SQLiteManualRepository(conn)
        categories = SQLiteCategoryRepository(conn)
        # md_to_html trivial para no depender de la lib markdown en los tests
        return ManualService(
            repo,
            renderer=renderer,
            ai=ai,
            md_to_html=lambda t: f"<md>{t}</md>",
            categories=categories,
            extractor=extractor,
            worker_ai=worker_ai,
        )
    return make


def test_create_manual_persiste(service_factory):
    svc = service_factory()
    m = svc.create_manual("Macro X", ManualType.TECNICO, "Macros")
    assert m.id is not None
    assert len(svc.list_manuals()) == 1


def test_rename_manual_cambia_el_titulo(service_factory):
    svc = service_factory()
    m = svc.create_manual("Título viejo", ManualType.TECNICO, "Python")
    svc.rename_manual(m.id, "Título nuevo")
    assert svc.get_manual(m.id).title == "Título nuevo"


def test_rename_manual_recorta_espacios(service_factory):
    svc = service_factory()
    m = svc.create_manual("X", ManualType.TECNICO, "Python")
    svc.rename_manual(m.id, "  Con espacios  ")
    assert svc.get_manual(m.id).title == "Con espacios"


def test_rename_manual_vacio_falla(service_factory):
    svc = service_factory()
    m = svc.create_manual("X", ManualType.TECNICO, "Python")
    with pytest.raises(ValueError, match="vacío"):
        svc.rename_manual(m.id, "   ")


def test_rename_no_afecta_pdf_de_versiones_viejas(service_factory):
    # Las versiones (y sus PDFs) son inmutables: renombrar no las toca.
    svc = service_factory(renderer=FakeRenderer())
    m = svc.create_manual("Original", ManualType.FUNCIONAL, "Power Apps")
    v = svc.save_version(m.id, [Section("Intro", "<p>x</p>", 0)])
    svc.rename_manual(m.id, "Renombrado")
    # El PDF viejo sigue con el título original "horneado"
    assert svc.get_version_pdf(v.id) == b"%PDF fake Original v1"


def test_save_version_genera_pdf_y_versiona(service_factory):
    svc = service_factory(renderer=FakeRenderer())
    m = svc.create_manual("Manual A", ManualType.FUNCIONAL, "Power Apps")

    v1 = svc.save_version(m.id, [Section("Intro", "<p>hola</p>", 0)], "primera")
    v2 = svc.save_version(m.id, [Section("Intro", "<p>chau</p>", 0)], "segunda")

    assert v1.version == 1
    assert v2.version == 2
    pdf = svc.get_version_pdf(v2.id)
    assert pdf == b"%PDF fake Manual A v2"


def test_save_version_combina_secciones_en_orden(service_factory):
    svc = service_factory(renderer=FakeRenderer())
    m = svc.create_manual("M", ManualType.TECNICO, "Python")
    secs = [Section("Segunda", "<p>2</p>", 1), Section("Primera", "<p>1</p>", 0)]
    v = svc.save_version(m.id, secs)
    assert v.content_html.index("Primera") < v.content_html.index("Segunda")


def test_save_version_sin_renderer_no_rompe(service_factory):
    svc = service_factory()  # sin renderer (ej: GTK no instalado todavía)
    m = svc.create_manual("M", ManualType.TECNICO, "Python")
    v = svc.save_version(m.id, [Section("X", "<p>x</p>")])
    assert v.pdf_blob is None


def test_category_hint_resuelve_el_ai_hint(service_factory):
    svc = service_factory()
    # "Power Apps" tiene ai_hint sembrado que menciona Power Platform
    assert "Power Platform" in svc.category_hint("Power Apps")
    # Una etiqueta inexistente devuelve la etiqueta misma
    assert svc.category_hint("Inexistente") == "Inexistente"


def test_ai_generate_usa_el_prompt_y_el_hint(service_factory):
    ai = FakeAI("## Manual\ncontenido")
    svc = service_factory(ai=ai)
    hint = svc.category_hint("Power Apps")  # resuelto en el "hilo principal"
    out = svc.ai_generate(
        topic="Aprobación de facturas", tipo=ManualType.FUNCIONAL, categoria_hint=hint
    )
    assert out == "## Manual\ncontenido"
    assert "FUNCIONAL" in ai.last_system
    assert "Aprobación de facturas" in ai.last_user
    # El hint de la categoría llega al prompt
    assert "Power Platform" in ai.last_user


def test_ai_generate_inyecta_autor_y_fecha_de_hoy(service_factory):
    from datetime import date

    ai = FakeAI()
    svc = service_factory(ai=ai)
    svc.ai_generate(
        topic="x", tipo=ManualType.FUNCIONAL, categoria_hint="Power Apps", author="Felipe Páez"
    )
    assert "Felipe Páez" in ai.last_user
    assert "Versionamiento" in ai.last_user
    assert date.today().strftime("%d/%m/%Y") in ai.last_user


def test_ai_generate_funcional_inyecta_responsable_area_y_fecha(service_factory):
    ai = FakeAI()
    svc = service_factory(ai=ai)
    svc.ai_generate(
        topic="x", tipo=ManualType.FUNCIONAL, categoria_hint="Power Apps",
        author="Felipe Páez", area="Finanzas", fecha="01/01/2030",
    )
    user = ai.last_user
    assert "Datos generales" in user
    assert "Responsable | Felipe Páez" in user
    assert "Área | Finanzas" in user
    assert "Fecha | 01/01/2030" in user
    # Regresión: debe instruir a NO crear una segunda sección de Datos generales
    assert "NO crees una segunda" in user
    # Y solo debe haber UN encabezado de la sección en la estructura
    assert user.count("## Datos generales") == 1


def test_ai_generate_tecnico_no_inyecta_datos_generales(service_factory):
    ai = FakeAI()
    svc = service_factory(ai=ai)
    svc.ai_generate(
        topic="x", tipo=ManualType.TECNICO, categoria_hint="Python",
        author="Felipe", area="Finanzas",
    )
    # El manual técnico no tiene sección «Datos generales»: no se fuerza nada de eso.
    assert "Responsable | Felipe" not in ai.last_user


def test_ai_generate_sin_fecha_usa_la_de_hoy(service_factory):
    from datetime import date

    ai = FakeAI()
    svc = service_factory(ai=ai)
    svc.ai_generate(topic="x", tipo=ManualType.FUNCIONAL, categoria_hint="Power Apps",
                    author="Felipe", area="Finanzas")  # sin fecha
    assert date.today().strftime("%d/%m/%Y") in ai.last_user


def test_ai_from_package_funcional_inyecta_datos_generales(service_factory):
    pkg = ExtractedPackage(kind="power-automate-flow", name="Flujo X",
                           summary_markdown="# Flujo X\n- Paso")
    ai = FakeAI()
    svc = service_factory(ai=ai, extractor=FakeExtractor(pkg))
    svc.ai_from_package(
        extracted=pkg, tipo=ManualType.FUNCIONAL, categoria_hint="Power Automate",
        author="Ana", area="RRHH", fecha="15/03/2031",
    )
    assert "Responsable | Ana" in ai.last_user
    assert "Área | RRHH" in ai.last_user
    assert "Fecha | 15/03/2031" in ai.last_user


def test_ai_from_package_separa_responsable_de_desarrollador(service_factory):
    # Responsable (ejecuta) → Datos generales; Desarrollador (programa) → Versionamiento.
    pkg = ExtractedPackage(kind="power-automate-flow", name="Flujo X",
                           summary_markdown="# Flujo X\n- Paso")
    ai = FakeAI()
    svc = service_factory(ai=ai, extractor=FakeExtractor(pkg))
    svc.ai_from_package(
        extracted=pkg, tipo=ManualType.FUNCIONAL, categoria_hint="Power Automate",
        author="Ana", area="RRHH", fecha="15/03/2031", developer="Beto",
    )
    assert "Responsable | Ana" in ai.last_user
    # El autor de la v1.0 es el desarrollador, no el responsable
    assert "versión 1.0 | 15/03/2031 | Beto | Versión inicial" in ai.last_user


def test_diff_for_primera_importacion_no_tiene_cambios(service_factory):
    from src.infrastructure.package_snapshot_repository import (
        SQLitePackageSnapshotRepository,
    )
    from src.infrastructure.db import connect, init_db

    conn = connect(":memory:")
    init_db(conn)
    svc = ManualService(
        SQLiteManualRepository(conn),
        categories=SQLiteCategoryRepository(conn),
        snapshots=SQLitePackageSnapshotRepository(conn),
    )
    sol = ExtractedPackage(
        kind="power-platform-solution", name="Sol", summary_markdown="# Sol",
        unique_name="SolX", version="1.0.0.1",
        components=[ExtractedPackage(kind="power-automate-flow", name="F1", summary_markdown="# a")],
    )
    diff = svc.diff_for(sol)
    assert diff.is_first_import is True
    assert diff.has_changes is False


def test_diff_for_detecta_cambios_tras_guardar_snapshot(service_factory):
    from src.infrastructure.package_snapshot_repository import (
        SQLitePackageSnapshotRepository,
    )
    from src.infrastructure.db import connect, init_db

    conn = connect(":memory:")
    init_db(conn)
    svc = ManualService(
        SQLiteManualRepository(conn),
        categories=SQLiteCategoryRepository(conn),
        snapshots=SQLitePackageSnapshotRepository(conn),
    )

    def sol(comps, version):
        return ExtractedPackage(
            kind="power-platform-solution", name="Sol", summary_markdown="# Sol",
            unique_name="SolX", version=version,
            components=[ExtractedPackage(kind="power-automate-flow", name=n, summary_markdown=md)
                        for n, md in comps],
        )

    v1 = sol([("F1", "# a"), ("F2", "# b")], "1.0.0.1")
    svc.save_snapshot(v1)
    # Nueva versión: F1 igual, F2 cambió, F2 fuera y entra F3.
    v2 = sol([("F1", "# a"), ("F3", "# c")], "1.0.0.2")
    diff = svc.diff_for(v2)
    assert diff.deprecated == ["F2"]
    assert diff.added == ["F3"]
    assert diff.version_from == "1.0.0.1" and diff.version_to == "1.0.0.2"


def test_ai_from_package_pasa_version_y_diff_al_prompt(service_factory):
    from src.domain.change_tracking import DiffResult

    pkg = ExtractedPackage(kind="power-automate-flow", name="MiFlujo",
                           summary_markdown="# F", unique_name="MiFlujo", version="2.0")
    ai = FakeAI()
    svc = service_factory(ai=ai, extractor=FakeExtractor(pkg))
    diff = DiffResult(version_from="1.0", version_to="2.0", modified=["MiFlujo"])
    svc.ai_from_package(
        extracted=pkg, tipo=ManualType.TECNICO, categoria_hint="Power Automate", diff=diff,
    )
    assert "2.0" in ai.last_user
    assert "Cambios respecto a la versión anterior" in ai.last_user


def test_ai_document_code_incluye_el_codigo(service_factory):
    ai = FakeAI()
    svc = service_factory(ai=ai)
    svc.ai_document_code(code="def foo(): return 1", tipo=ManualType.TECNICO, categoria_hint="Python")
    assert "def foo(): return 1" in ai.last_user


def test_extract_package_usa_el_extractor(service_factory):
    pkg = ExtractedPackage(kind="power-automate-flow", name="Mi Flujo",
                           summary_markdown="# Mi Flujo\n- Paso 1")
    svc = service_factory(extractor=FakeExtractor(pkg))
    out = svc.extract_package(b"zip-bytes", "flujo.zip")
    assert out.name == "Mi Flujo"


def test_extract_package_sin_extractor_falla_claro(service_factory):
    svc = service_factory()  # sin extractor
    with pytest.raises(RuntimeError, match="extractor"):
        svc.extract_package(b"x", "x.zip")


def test_ai_from_package_lleva_estructura_y_nombre_al_prompt(service_factory):
    pkg = ExtractedPackage(kind="power-automate-flow", name="Aprobación de Facturas",
                           summary_markdown="# Flujo\n- Obtener detalles\n- Enviar correo")
    ai = FakeAI("## Manual\ncontenido")
    svc = service_factory(ai=ai, extractor=FakeExtractor(pkg))
    out = svc.ai_from_package(
        extracted=pkg, tipo=ManualType.TECNICO, categoria_hint="Power Automate"
    )
    assert out == "## Manual\ncontenido"
    # La estructura REAL extraída llega al prompt
    assert "Obtener detalles" in ai.last_user
    assert "Aprobación de Facturas" in ai.last_user
    assert "TÉCNICO" in ai.last_system


def test_ai_complement_lleva_manual_actual_e_instrucciones_al_prompt(service_factory):
    ai = FakeAI("## Manual integrado\ntodo junto")
    svc = service_factory(ai=ai)
    out = svc.ai_complement(
        current_markdown="## Objetivo\nDocumentar el flujo de facturas",
        instructions="agregá que también notifica por Teams",
        tipo=ManualType.TECNICO, categoria_hint="Power Automate",
    )
    assert out == "## Manual integrado\ntodo junto"
    # Tanto el manual actual como la indicación nueva llegan al prompt
    assert "Documentar el flujo de facturas" in ai.last_user
    assert "notifica por Teams" in ai.last_user
    # Debe pedir integrar sin duplicar ni perder
    assert "COMPLETO" in ai.last_user


def test_ai_complement_ancla_las_secciones_existentes(service_factory):
    ai = FakeAI()
    svc = service_factory(ai=ai)
    svc.ai_complement(
        current_markdown="## Datos generales\n...\n## Objetivo\n...\n## Alcance\n...",
        instructions="agregá algo",
        tipo=ManualType.FUNCIONAL, categoria_hint="Power Apps",
    )
    # Le pasa el conjunto exacto de secciones para que no duplique
    assert "EXACTAMENTE estas secciones" in ai.last_user
    assert "Datos generales" in ai.last_user
    assert "Objetivo" in ai.last_user
    assert "Alcance" in ai.last_user


def test_pending_slots_y_questions_y_fill_flujo_completo(service_factory):
    manual = (
        "## Datos generales\n"
        "Responsable | [COMPLETAR]\n"
        "Área | [COMPLETAR]\n"
    )
    # La IA devuelve una pregunta por línea, una por hueco.
    ai = FakeAI("¿Quién es el responsable?\n¿Cuál es el área?")
    svc = service_factory(ai=ai)

    slots = svc.pending_slots(manual)
    assert len(slots) == 2

    questions = svc.ai_questions_for_pending(manual)
    assert questions == ["¿Quién es el responsable?", "¿Cuál es el área?"]
    # El contexto de los huecos llega al prompt de la IA
    assert "Datos generales" in ai.last_user

    filled = svc.fill_pending(manual, ["Ana López", "Finanzas"])
    assert "Responsable | Ana López" in filled
    assert "Área | Finanzas" in filled
    assert "[COMPLETAR]" not in filled


def test_ai_questions_sin_huecos_no_llama_a_la_ia(service_factory):
    ai = FakeAI()
    svc = service_factory(ai=ai)
    assert svc.ai_questions_for_pending("## Todo\ncompleto") == []
    assert ai.last_user is None  # no se llamó a la IA


def test_ai_from_package_atomico_una_sola_llamada(service_factory):
    # Un paquete sin sub-componentes → una sola llamada, sin orquestar.
    pkg = ExtractedPackage(kind="power-automate-flow", name="Flujo",
                           summary_markdown="# Flujo\n- paso")
    orchestrator = RecordingAI("manual")
    worker = RecordingAI("seccion")
    svc = service_factory(ai=orchestrator, worker_ai=worker)
    svc.ai_from_package(extracted=pkg, tipo=ManualType.TECNICO, categoria_hint="PA")
    assert len(orchestrator.calls) == 1
    assert worker.calls == []  # el obrero no se usa en paquetes atómicos


def test_ai_from_package_tecnico_orquesta_con_obrero(service_factory):
    # Manual TÉCNICO (el pesado): el OBRERO redacta cada componente, orquestador integra.
    comp1 = ExtractedPackage(kind="power-automate-flow", name="Flujo1",
                             summary_markdown="# Flujo1")
    comp2 = ExtractedPackage(kind="power-apps-canvas", name="App1",
                             summary_markdown="# App1")
    solution = ExtractedPackage(
        kind="power-platform-solution", name="MiSolución",
        summary_markdown="# MiSolución", components=[comp1, comp2],
    )
    orchestrator = RecordingAI("MANUAL INTEGRADO")
    worker = RecordingAI("sección redactada")
    svc = service_factory(ai=orchestrator, worker_ai=worker)

    out = svc.ai_from_package(
        extracted=solution, tipo=ManualType.TECNICO, categoria_hint="Power Platform",
        author="Ana", area="RRHH",
    )
    # El OBRERO redactó una vez por componente (el grueso, modelo chico)
    assert len(worker.calls) == 2
    assert "Flujo1" in worker.calls[0][1]
    assert "App1" in worker.calls[1][1]
    # El ORQUESTADOR integró una sola vez (modelo potente) y devolvió el resultado
    assert len(orchestrator.calls) == 1
    assert "MiSolución" in orchestrator.calls[0][1]
    assert out == "MANUAL INTEGRADO"


def test_funcional_usa_el_orquestador_para_las_secciones_no_el_obrero(service_factory):
    # El FUNCIONAL (breve) usa el ORQUESTADOR para redactar cada componente: el
    # obrero no se usa (se colgaba y las secciones son cortas → barato y estable).
    comp1 = ExtractedPackage(kind="power-automate-flow", name="Flujo1", summary_markdown="# F1")
    comp2 = ExtractedPackage(kind="power-apps-canvas", name="App1", summary_markdown="# A1")
    solution = ExtractedPackage(
        kind="power-platform-solution", name="MiSolución",
        summary_markdown="# MiSolución", components=[comp1, comp2],
    )
    orchestrator = RecordingAI("INTEGRADO")
    worker = RecordingAI("sec obrero")
    svc = service_factory(ai=orchestrator, worker_ai=worker)

    svc.ai_from_package(
        extracted=solution, tipo=ManualType.FUNCIONAL, categoria_hint="Power Platform",
    )
    # El obrero NO se usa para el funcional
    assert worker.calls == []
    # El orquestador hace las 2 secciones + la integración = 3 llamadas
    assert len(orchestrator.calls) == 3


def test_orquesta_sin_obrero_usa_el_orquestador_para_todo(service_factory):
    # Sin worker_ai configurado → degrada: el orquestador hace todo.
    comp = ExtractedPackage(kind="power-automate-flow", name="F", summary_markdown="# F")
    solution = ExtractedPackage(kind="power-platform-solution", name="S",
                                summary_markdown="# S", components=[comp, comp])
    orchestrator = RecordingAI("ok")
    svc = service_factory(ai=orchestrator)  # sin worker
    svc.ai_from_package(extracted=solution, tipo=ManualType.TECNICO, categoria_hint="PP")
    # 2 secciones + 1 integración = 3 llamadas, todas al orquestador
    assert len(orchestrator.calls) == 3


def test_orquesta_reporta_progreso_por_componente(service_factory):
    comp1 = ExtractedPackage(kind="power-automate-flow", name="Flujo1", summary_markdown="# F1")
    comp2 = ExtractedPackage(kind="power-apps-canvas", name="App1", summary_markdown="# A1")
    solution = ExtractedPackage(
        kind="power-platform-solution", name="Sol", summary_markdown="# Sol",
        components=[comp1, comp2],
    )
    svc = service_factory(ai=RecordingAI("INTEGRADO"), worker_ai=RecordingAI("sec"))
    msgs: list[str] = []
    svc.ai_from_package(
        extracted=solution, tipo=ManualType.TECNICO, categoria_hint="PP",
        progress=msgs.append,
    )
    # Reporta cada componente (con índice/total y nombre) y la integración final.
    assert any("1/2" in m and "Flujo1" in m for m in msgs)
    assert any("2/2" in m and "App1" in m for m in msgs)
    assert any("integr" in m.lower() for m in msgs)


def test_obrero_401_cae_al_modelo_principal_y_completa(service_factory):
    # El obrero da 401 (no autorizado) → se usa el modelo principal para las
    # secciones, así el manual se genera COMPLETO igual (no cascarón).
    from src.domain.ports import AIAuthError

    class AuthFailWorker(AIProvider):
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, system_prompt: str, user_prompt: str) -> str:
            self.calls += 1
            raise AIAuthError("401")

    comp1 = ExtractedPackage(kind="power-automate-flow", name="F1", summary_markdown="# F1")
    comp2 = ExtractedPackage(kind="power-automate-flow", name="F2", summary_markdown="# F2")
    solution = ExtractedPackage(
        kind="power-platform-solution", name="Sol", summary_markdown="# Sol",
        components=[comp1, comp2],
    )
    orchestrator = RecordingAI("INTEGRADO")
    worker = AuthFailWorker()
    svc = service_factory(ai=orchestrator, worker_ai=worker)
    msgs: list[str] = []
    out = svc.ai_from_package(
        extracted=solution, tipo=ManualType.TECNICO, categoria_hint="PP", progress=msgs.append,
    )
    assert out == "INTEGRADO"
    # El obrero intentó UNA vez (la 1ra), falló auth → el resto va al principal.
    assert worker.calls == 1
    # El principal redactó las 2 secciones + integró = 3 llamadas.
    assert len(orchestrator.calls) == 3
    # Avisó del fallback.
    assert any("obrero" in m.lower() and "401" in m for m in msgs)


def test_obrero_y_principal_401_aborta(service_factory):
    from src.domain.ports import AIAuthError

    class AuthFail(AIProvider):
        def complete(self, system_prompt: str, user_prompt: str) -> str:
            raise AIAuthError("401 no autorizado")

    comp = ExtractedPackage(kind="power-automate-flow", name="F", summary_markdown="# F")
    solution = ExtractedPackage(kind="power-platform-solution", name="S",
                                summary_markdown="# S", components=[comp, comp])
    svc = service_factory(ai=AuthFail(), worker_ai=AuthFail())
    with pytest.raises(AIAuthError):
        svc.ai_from_package(extracted=solution, tipo=ManualType.TECNICO, categoria_hint="PP")


def test_orquesta_integracion_que_falla_no_pierde_lo_redactado(service_factory):
    class FailingOrch(AIProvider):
        def complete(self, system_prompt: str, user_prompt: str) -> str:
            raise RuntimeError("timeout en la integración")

    comp1 = ExtractedPackage(kind="power-automate-flow", name="F1", summary_markdown="# F1")
    comp2 = ExtractedPackage(kind="power-automate-flow", name="F2", summary_markdown="# F2")
    solution = ExtractedPackage(
        kind="power-platform-solution", name="Sol", summary_markdown="# Sol",
        components=[comp1, comp2],
    )
    worker = RecordingAI("## Sección redactada\ncontenido del obrero")
    svc = service_factory(ai=FailingOrch(), worker_ai=worker)
    out = svc.ai_from_package(extracted=solution, tipo=ManualType.TECNICO, categoria_hint="PP")
    # No explota: devuelve lo redactado por los obreros (modo degradado) + un aviso.
    assert "contenido del obrero" in out
    assert "[COMPLETAR]" in out


def test_orquesta_resiliente_un_componente_que_falla_no_mata_todo(service_factory):
    class FlakyWorker(AIProvider):
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, system_prompt: str, user_prompt: str) -> str:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("timeout simulado")
            return "sección ok"

    comp1 = ExtractedPackage(kind="power-automate-flow", name="Flujo1", summary_markdown="# F1")
    comp2 = ExtractedPackage(kind="power-automate-flow", name="Flujo2", summary_markdown="# F2")
    solution = ExtractedPackage(
        kind="power-platform-solution", name="Sol", summary_markdown="# Sol",
        components=[comp1, comp2],
    )
    orchestrator = RecordingAI("INTEGRADO")
    svc = service_factory(ai=orchestrator, worker_ai=FlakyWorker())
    out = svc.ai_from_package(extracted=solution, tipo=ManualType.TECNICO, categoria_hint="PP")
    # NO explota: integra igual. El componente que falló entra como placeholder.
    assert out == "INTEGRADO"
    assert len(orchestrator.calls) == 1
    integ = orchestrator.calls[0][1]
    assert "Flujo1" in integ and "[COMPLETAR]" in integ


def test_ai_sin_proveedor_falla_claro(service_factory):
    svc = service_factory()  # sin IA
    with pytest.raises(RuntimeError, match="proveedor de IA"):
        svc.ai_generate(topic="x", tipo=ManualType.TECNICO, categoria_hint="Python")


def test_markdown_to_section_convierte(service_factory):
    svc = service_factory()
    sec = svc.markdown_to_section("Intro", "# Hola", order=2)
    assert sec.title == "Intro"
    assert sec.content_html == "<md># Hola</md>"
    assert sec.order == 2


# --- Categorías (catálogo editable) ---------------------------------------

def test_categorias_por_defecto_sembradas(service_factory):
    svc = service_factory()
    labels = [c.label for c in svc.list_categories()]
    assert "Power Apps" in labels
    assert "Macros" in labels
    # Las tecnologías con knowledge pack tienen su categoría (para rutear bien).
    assert "Power Automate" in labels
    assert "Dataverse" in labels
    assert "Solution" in labels  # categoría que abarca toda una Solution


def test_categorias_de_knowledge_se_migran_en_db_vieja():
    # Simula una DB vieja (sin Power Automate/Dataverse) y verifica que init_db las suma.
    from src.infrastructure.db import connect, init_db

    conn = connect(":memory:")
    conn.execute(
        "CREATE TABLE categories (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "label TEXT NOT NULL UNIQUE, ai_hint TEXT NOT NULL DEFAULT '')"
    )
    conn.execute("INSERT INTO categories (label, ai_hint) VALUES ('Vieja', 'algo')")
    conn.commit()
    init_db(conn)  # no está vacía → no siembra defaults, pero SÍ migra las de knowledge
    labels = [r["label"] for r in conn.execute("SELECT label FROM categories").fetchall()]
    assert "Power Automate" in labels
    assert "Dataverse" in labels
    assert "Solution" in labels
    assert "Vieja" in labels  # no pisa lo que ya había


def test_add_category(service_factory):
    svc = service_factory()
    svc.add_category("SharePoint", "listas y bibliotecas de SharePoint")
    labels = [c.label for c in svc.list_categories()]
    assert "SharePoint" in labels


def test_add_category_duplicada_falla(service_factory):
    svc = service_factory()
    with pytest.raises(ValueError, match="Ya existe"):
        svc.add_category("Power Apps")


def test_rename_category_reapunta_manuales(service_factory):
    svc = service_factory()
    m = svc.create_manual("M", ManualType.FUNCIONAL, "Power Apps")
    svc.rename_category("Power Apps", "Power Platform")
    # El manual sigue su categoría renombrada
    assert svc.get_manual(m.id).category == "Power Platform"
    labels = [c.label for c in svc.list_categories()]
    assert "Power Platform" in labels and "Power Apps" not in labels


def test_delete_category_en_uso_falla(service_factory):
    svc = service_factory()
    svc.create_manual("M", ManualType.FUNCIONAL, "Macros")
    with pytest.raises(ValueError, match="No se puede borrar"):
        svc.delete_category("Macros")


def test_delete_category_libre_funciona(service_factory):
    svc = service_factory()
    svc.add_category("Temporal")
    svc.delete_category("Temporal")
    assert "Temporal" not in [c.label for c in svc.list_categories()]


# --- Exportar a Word --------------------------------------------------------

def _svc_con_docx(docx_renderer=None):
    conn = connect(":memory:")
    init_db(conn)
    return ManualService(SQLiteManualRepository(conn), docx_renderer=docx_renderer)


def test_build_docx_delega_en_el_renderer():
    from src.domain.entities import Manual, ManualVersion
    from src.domain.ports import DocxRenderer

    class FakeDocx(DocxRenderer):
        def render(self, manual, version) -> bytes:
            return f"DOCX {manual.title} v{version.version}".encode()

    svc = _svc_con_docx(FakeDocx())
    assert svc.docx_ready
    m = Manual(title="Cuentas", type=ManualType.TECNICO, category="Power Automate")
    out = svc.build_docx(m, ManualVersion(version=3, content_html=""))
    assert out == b"DOCX Cuentas v3"


def test_build_docx_sin_renderer_falla():
    from src.domain.entities import Manual, ManualVersion

    svc = _svc_con_docx(None)
    assert not svc.docx_ready
    with pytest.raises(RuntimeError, match="Word"):
        svc.build_docx(
            Manual(title="X", type=ManualType.TECNICO, category="X"),
            ManualVersion(version=1, content_html=""),
        )


# --- Integrar un paquete en un manual existente -----------------------------

def test_ai_complement_with_package_integra_la_estructura(service_factory):
    ai = FakeAI("## Manual ya integrado")
    svc = service_factory(ai=ai)
    pkg = ExtractedPackage(
        kind="power-bi-model", name="Tablero",
        summary_markdown="## Tabla: Ventas\n- Monto (double)\nMedida: Total = SUM(Monto)",
    )
    out = svc.ai_complement_with_package(
        current_markdown="# Manual\n## Datos generales\nProceso X.",
        extracted=pkg, tipo=ManualType.TECNICO, categoria_hint="Power BI",
    )
    assert out == "## Manual ya integrado"
    # El prompt llevó la estructura del paquete Y el manual actual a complementar.
    assert "## Tabla: Ventas" in ai.last_user
    assert "Total = SUM(Monto)" in ai.last_user
    assert "Manual actual" in ai.last_user
    assert "ESTRUCTURA EXTRA" in ai.last_user  # se enmarca como material extraído


def test_document_package_section_una_llamada_chica_por_componente(service_factory):
    # Anti-timeout: cada componente = UNA llamada de obrero, NO una llamada grande
    # que re-emita todo. Para un Power BI (modelo + reporte) → 2 llamadas.
    ai = RecordingAI("SECCION")
    svc = service_factory(ai=ai)
    pkg = ExtractedPackage(
        kind="power-bi", name="Tablero", summary_markdown="resumen",
        components=[
            ExtractedPackage(kind="power-bi-model", name="Modelo", summary_markdown="## Tabla"),
            ExtractedPackage(kind="power-bi-report", name="Reporte", summary_markdown="## Página"),
        ],
    )
    out = svc.ai_document_package_section(
        extracted=pkg, tipo=ManualType.TECNICO, categoria_hint="Power BI")
    assert len(ai.calls) == 2          # una por componente, ninguna re-emite el manual
    assert out.count("SECCION") == 2   # las dos secciones, unidas para adjuntar


def test_document_package_section_atomico_una_sola_llamada(service_factory):
    ai = RecordingAI("S")
    svc = service_factory(ai=ai)
    pkg = ExtractedPackage(kind="excel-vba", name="Macro", summary_markdown="## Módulo")
    out = svc.ai_document_package_section(
        extracted=pkg, tipo=ManualType.TECNICO, categoria_hint="Macros")
    assert len(ai.calls) == 1          # atómico: la unidad es el paquete mismo
    assert out == "S"


def test_document_package_section_resiliente_si_falla_un_componente(service_factory):
    # Si un componente explota, deja [COMPLETAR] y sigue con el resto (no pierde todo).
    class FlakyAI(AIProvider):
        def __init__(self):
            self.n = 0
        def complete(self, system_prompt, user_prompt):
            self.n += 1
            if self.n == 1:
                raise RuntimeError("boom")
            return "OK2"
    svc = service_factory(ai=FlakyAI())
    pkg = ExtractedPackage(
        kind="power-bi", name="T", summary_markdown="r",
        components=[
            ExtractedPackage(kind="power-bi-model", name="Modelo", summary_markdown="a"),
            ExtractedPackage(kind="power-bi-report", name="Reporte", summary_markdown="b"),
        ],
    )
    out = svc.ai_document_package_section(
        extracted=pkg, tipo=ManualType.TECNICO, categoria_hint="Power BI")
    assert "[COMPLETAR]" in out and "Modelo" in out   # el que falló, marcado
    assert "OK2" in out                                # el otro, redactado
