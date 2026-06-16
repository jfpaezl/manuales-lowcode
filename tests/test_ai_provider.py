"""Tests del proveedor OpenAI-compatible (helper de listado de modelos)."""
import sys
import types

import pytest

from src.infrastructure.ai import openai_compatible_provider as prov
from src.infrastructure.ai.openai_compatible_provider import AIConfig, OpenAICompatibleProvider


class _FakeBadRequest(Exception):
    """Imita openai.BadRequestError: trae status_code y un mensaje del proveedor."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _provider_con_create(monkeypatch, create):
    """Arma un provider cuyo cliente openai usa el `create` que le pasamos.

    Mockea el módulo openai entero (nada de red): el cliente expone
    chat.completions.create.
    """
    def fake_openai(**_kwargs):
        completions = types.SimpleNamespace(create=create)
        return types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=completions)
        )

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=fake_openai))
    return OpenAICompatibleProvider(
        AIConfig(api_key="key", base_url="https://x/v1", model="kimi-k2.7-code")
    )


def _respuesta(texto: str):
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=texto))]
    )


def test_complete_reintenta_sin_temperature_cuando_el_modelo_la_rechaza(monkeypatch):
    # Modelo tipo Kimi/Moonshot: rechaza cualquier temperature != 1 con un 400.
    llamadas = []

    def create(**kwargs):
        llamadas.append(kwargs)
        if "temperature" in kwargs:
            raise _FakeBadRequest(
                "Error code: 400 - {'error': {'message': 'Error from provider "
                "(Moonshot AI): invalid temperature: only 1 is allowed for this model'}}"
            )
        return _respuesta("listo")

    provider = _provider_con_create(monkeypatch, create)
    out = provider.complete("sys", "user")

    assert out == "listo"
    assert len(llamadas) == 2                      # falló con temp, reintentó sin temp
    assert "temperature" in llamadas[0]            # primer intento: con temperature
    assert "temperature" not in llamadas[1]        # reintento: sin temperature


def test_complete_no_reintenta_otros_400(monkeypatch):
    # Un 400 que NO es por temperature debe propagar, no enmascararse con un reintento.
    llamadas = []

    def create(**kwargs):
        llamadas.append(kwargs)
        raise _FakeBadRequest("Error code: 400 - invalid messages: empty content")

    provider = _provider_con_create(monkeypatch, create)
    with pytest.raises(_FakeBadRequest):
        provider.complete("sys", "user")
    assert len(llamadas) == 1                       # no reintenta


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
