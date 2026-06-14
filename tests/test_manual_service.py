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


def test_ai_from_package_solution_orquesta_con_obrero(service_factory):
    # Solution con 2 componentes → obrero redacta cada uno, orquestador integra.
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
        extracted=solution, tipo=ManualType.FUNCIONAL, categoria_hint="Power Platform",
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


def test_add_category(service_factory):
    svc = service_factory()
    svc.add_category("Power Automate", "flujos de Power Automate")
    labels = [c.label for c in svc.list_categories()]
    assert "Power Automate" in labels


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
