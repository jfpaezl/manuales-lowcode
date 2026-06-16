"""Knowledge packs: resolución por kind, por categoría y por CONTENIDO (salvaguarda)."""
from src.application.knowledge import (
    knowledge_for,
    knowledge_for_category,
    knowledge_for_text,
)


def test_knowledge_for_kind_conocido_y_desconocido():
    assert "columnas" in knowledge_for("dataverse-table").lower()
    assert knowledge_for("kind-inexistente") == ""


def test_category_resuelve_por_palabra_clave_del_hint():
    # Los hints de las categorías por defecto deben caer en el pack correcto.
    assert "pantallas" in knowledge_for_category("Power Apps (Power Platform)").lower()
    assert "módulos" in knowledge_for_category("macros (Excel/VBA/Office)").lower()
    assert "trigger" in knowledge_for_category("flujos de Power Automate").lower()
    assert "columnas" in knowledge_for_category("tablas de Dataverse").lower()


def test_category_sin_match_devuelve_vacio():
    # Python no tiene pack todavía → sin ruido.
    assert knowledge_for_category("scripts de Python") == ""
    assert knowledge_for_category("") == ""


def test_salvaguarda_detecta_tecnologia_por_contenido():
    # Sin kind ni categoría: detecta la tecnología leyendo el material real.
    assert knowledge_for_text("usa OpenApiConnection y runAfter") == knowledge_for("power-automate-flow")
    assert knowledge_for_text("Sub Main()\n  Dim x\nEnd Sub") == knowledge_for("excel-vba")
    assert knowledge_for_text("la pantalla hace Patch( y Navigate(") == knowledge_for("power-apps-canvas")
    assert knowledge_for_text("la entidad tiene LogicalName y RequiredLevel") == knowledge_for("dataverse-table")
    assert knowledge_for_text("un texto cualquiera sin señales") == ""


def test_hints_de_categorias_default_rutean_al_pack_correcto():
    # Cada categoría sembrada con pack debe llevar a SU knowledge pack.
    from src.infrastructure.db import _DEFAULT_CATEGORIES

    hints = {label: hint for label, hint in _DEFAULT_CATEGORIES}
    assert knowledge_for_category(hints["Power Apps"]) == knowledge_for("power-apps-canvas")
    assert knowledge_for_category(hints["Power Automate"]) == knowledge_for("power-automate-flow")
    assert knowledge_for_category(hints["Dataverse"]) == knowledge_for("dataverse-table")
    assert knowledge_for_category(hints["Macros"]) == knowledge_for("excel-vba")
