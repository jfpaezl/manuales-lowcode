import pytest

from src.domain.entities import Manual, ManualType, ManualVersion, Section
from src.infrastructure.db import connect, init_db
from src.infrastructure.manual_repository import SQLiteManualRepository


@pytest.fixture
def repo():
    conn = connect(":memory:")
    init_db(conn)
    yield SQLiteManualRepository(conn)
    conn.close()


def _manual() -> Manual:
    return Manual(
        title="Manual Power Apps",
        type=ManualType.FUNCIONAL,
        category="Power Apps",
        description="Demo",
    )


def test_add_asigna_id(repo):
    m = repo.add(_manual())
    assert m.id is not None


def test_get_trae_el_manual(repo):
    m = repo.add(_manual())
    traido = repo.get(m.id)
    assert traido is not None
    assert traido.title == "Manual Power Apps"
    assert traido.type is ManualType.FUNCIONAL
    assert traido.category == "Power Apps"


def test_list_devuelve_los_manuales(repo):
    repo.add(_manual())
    repo.add(_manual())
    assert len(repo.list()) == 2


def test_add_version_y_get_version_con_blob(repo):
    m = repo.add(_manual())
    v = ManualVersion(
        version=1,
        content_html="<h1>Hola</h1>",
        sections=[Section(title="Intro", content_html="<p>x</p>", order=0)],
        pdf_blob=b"%PDF-1.7 fake",
        change_note="primera versión",
    )
    saved = repo.add_version(m.id, v)
    assert saved.id is not None

    fetched = repo.get_version(saved.id)
    assert fetched.pdf_blob == b"%PDF-1.7 fake"
    assert fetched.sections[0].title == "Intro"
    assert fetched.content_hash == v.content_hash


def test_get_no_trae_blob_pesado(repo):
    m = repo.add(_manual())
    repo.add_version(m.id, ManualVersion(version=1, content_html="<p>a</p>", pdf_blob=b"x"))
    traido = repo.get(m.id)
    assert traido.versions[0].pdf_blob is None  # se pide aparte con get_version


def test_delete_borra_en_cascada(repo):
    m = repo.add(_manual())
    repo.add_version(m.id, ManualVersion(version=1, content_html="<p>a</p>"))
    repo.delete(m.id)
    assert repo.get(m.id) is None


def test_count_by_category(repo):
    repo.add(_manual())
    repo.add(_manual())
    assert repo.count_by_category("Power Apps") == 2
    assert repo.count_by_category("Macros") == 0


def test_reassign_category(repo):
    m = repo.add(_manual())
    repo.reassign_category("Power Apps", "Power Platform")
    assert repo.get(m.id).category == "Power Platform"
    assert repo.count_by_category("Power Apps") == 0
