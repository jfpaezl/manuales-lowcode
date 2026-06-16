"""Tests de la identidad de marca del PDF.

El _build_html del renderer usa solo Jinja (NO necesita GTK/WeasyPrint), así que
podemos verificar que la marca, el lema y el logo aparecen en la portada sin
generar el PDF de verdad.
"""
import base64

from src.domain.entities import Manual, ManualType, ManualVersion
from src.infrastructure.pdf.weasyprint_renderer import WeasyPrintRenderer


def _manual_y_version():
    m = Manual(title="Mi Manual", type=ManualType.FUNCIONAL, category="Power Apps")
    v = ManualVersion(version=1, content_html="<p>cuerpo</p>")
    return m, v


def test_marca_y_lema_en_la_portada():
    r = WeasyPrintRenderer(brand="ACME S.A.", tagline="Documentación interna")
    html = r._build_html(*_manual_y_version())
    assert "ACME S.A." in html
    assert "Documentación interna" in html


def test_sin_marca_usa_default():
    r = WeasyPrintRenderer()
    html = r._build_html(*_manual_y_version())
    assert "Mi Empresa" in html


def test_logo_se_embebe_como_data_uri(tmp_path):
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"\x89PNG\r\n fake bytes")
    r = WeasyPrintRenderer(brand="ACME", logo_path=str(logo))
    html = r._build_html(*_manual_y_version())
    assert "data:image/png;base64," in html
    # el contenido del archivo está codificado en el data URI
    assert base64.b64encode(b"\x89PNG\r\n fake bytes").decode() in html


def test_logo_inexistente_se_omite_sin_romper(tmp_path):
    r = WeasyPrintRenderer(brand="ACME", logo_path=str(tmp_path / "no-existe.png"))
    html = r._build_html(*_manual_y_version())
    assert "data:image" not in html       # no hay logo
    assert "ACME" in html                  # pero el resto sale igual


def test_set_identity_actualiza_en_caliente():
    r = WeasyPrintRenderer(brand="Viejo")
    r.set_identity(brand="Nuevo", tagline="Lema nuevo")
    html = r._build_html(*_manual_y_version())
    assert "Nuevo" in html and "Lema nuevo" in html
    assert "Viejo" not in html


def test_config_guarda_y_lee_identidad(tmp_path):
    from src.config import load_config, save_config

    p = tmp_path / "config.toml"
    save_config(
        p, db_path="x.db", api_key="k", base_url="u", model="m",
        brand_name="ACME S.A.", brand_tagline="Calidad", brand_logo="/ruta/logo.png",
    )
    c = load_config(p)
    assert c.brand_name == "ACME S.A."
    assert c.brand_tagline == "Calidad"
    assert c.brand_logo == "/ruta/logo.png"


def test_config_guarda_y_lee_timeout(tmp_path):
    # El timeout de la IA es configurable (modelos lentos como minimax necesitan más).
    from src.config import load_config, save_config

    p = tmp_path / "config.toml"
    save_config(p, db_path="x.db", api_key="k", base_url="u", model="m", timeout=300.0)
    c = load_config(p)
    assert c.ai is not None
    assert c.ai.timeout == 300.0


def test_config_timeout_default_cuando_no_esta(tmp_path):
    from src.config import load_config, save_config

    p = tmp_path / "config.toml"
    save_config(p, db_path="x.db", api_key="k", base_url="u", model="m")  # sin timeout
    c = load_config(p)
    assert c.ai.timeout == 300.0  # default razonable para modelos lentos


def test_config_guarda_y_lee_responsable_y_desarrollador(tmp_path):
    # Responsable (ejecuta) y Desarrollador (programa) son campos distintos y
    # ambos se recuerdan entre sesiones.
    from src.config import load_config, save_config

    p = tmp_path / "config.toml"
    save_config(
        p, db_path="x.db", api_key="k", base_url="u", model="m",
        author="Ana Responsable", area="Finanzas", developer="Beto Desarrollador",
    )
    c = load_config(p)
    assert c.author == "Ana Responsable"
    assert c.area == "Finanzas"
    assert c.developer == "Beto Desarrollador"
