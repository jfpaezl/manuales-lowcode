"""Tests del proveedor OpenAI-compatible (helper de listado de modelos)."""
import sys
import types

from src.infrastructure.ai import openai_compatible_provider as prov


def test_list_available_models_ordena_y_deduplica(monkeypatch):
    # Mockeamos el cliente openai: nada de red.
    def fake_client(**_kwargs):
        models = [types.SimpleNamespace(id="gpt-z"),
                  types.SimpleNamespace(id="gpt-a"),
                  types.SimpleNamespace(id="gpt-a")]  # duplicado a propósito
        return types.SimpleNamespace(
            models=types.SimpleNamespace(list=lambda: types.SimpleNamespace(data=models))
        )

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=fake_client))
    result = prov.list_available_models("key", "https://x/v1")
    assert result == ["gpt-a", "gpt-z"]  # ordenado y sin duplicados
