"""Fase 3: persistencia del snapshot de paquete (memoria del seguimiento de cambios)."""
from src.domain.change_tracking import ComponentSnapshot, PackageSnapshot, StoredSnapshot
from src.domain.entities import Manual, ManualType
from src.infrastructure.db import connect, init_db
from src.infrastructure.manual_repository import SQLiteManualRepository
from src.infrastructure.package_snapshot_repository import SQLitePackageSnapshotRepository


def _repo():
    conn = connect(":memory:")
    init_db(conn)
    # Dos manuales reales para que las FK del snapshot apunten a filas existentes.
    manuals = SQLiteManualRepository(conn)
    func = manuals.add(Manual(title="F", type=ManualType.FUNCIONAL, category="Otro"))
    tec = manuals.add(Manual(title="T", type=ManualType.TECNICO, category="Otro"))
    return SQLitePackageSnapshotRepository(conn), func.id, tec.id


def _stored(func, tec, unique_name="Sol", version="1.0.0.1", comps=None):
    comps = comps or [ComponentSnapshot("F1", "power-automate-flow", "h1")]
    return StoredSnapshot(
        snapshot=PackageSnapshot(unique_name=unique_name, version=version, components=comps),
        manual_func_id=func, manual_tec_id=tec,
    )


def test_guarda_y_recupera_snapshot():
    repo, func, tec = _repo()
    repo.save(_stored(func, tec))
    got = repo.get("Sol")
    assert got is not None
    assert got.snapshot.version == "1.0.0.1"
    assert got.manual_func_id == func
    assert got.manual_tec_id == tec
    assert [c.name for c in got.snapshot.components] == ["F1"]
    assert got.snapshot.components[0].fingerprint == "h1"


def test_get_inexistente_devuelve_none():
    repo, _, _ = _repo()
    assert repo.get("NoExiste") is None


def test_get_con_unique_name_vacio_devuelve_none():
    repo, _, _ = _repo()
    assert repo.get("") is None


def test_upsert_pisa_la_version_anterior():
    repo, func, tec = _repo()
    repo.save(_stored(func, tec, version="1.0.0.1", comps=[ComponentSnapshot("F1", "k", "h1")]))
    repo.save(_stored(func, tec, version="1.0.0.2", comps=[ComponentSnapshot("F1", "k", "h2")]))
    got = repo.get("Sol")
    assert got.snapshot.version == "1.0.0.2"
    assert got.snapshot.components[0].fingerprint == "h2"


def test_save_sin_unique_name_no_persiste():
    repo, func, tec = _repo()
    repo.save(_stored(func, tec, unique_name=""))
    assert repo.get("") is None
