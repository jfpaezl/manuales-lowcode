"""Adaptador de IA: cliente OpenAI-compatible.

UNA sola clase sirve para OpenCode Go, OpenRouter, Ollama, Groq... todos
hablan el mismo protocolo. Cambiás base_url + model en config.toml y listo.
Esa es la magia de programar contra un estándar y no contra un proveedor.
"""
from __future__ import annotations

from dataclasses import dataclass

from ...domain.ports import AIProvider


def list_available_models(api_key: str, base_url: str, timeout: float = 15.0) -> list[str]:
    """Lista los modelos disponibles para una conexión OpenAI-compatible.

    Usa el endpoint estándar GET /models. No todos los proveedores lo
    implementan igual: si falla, el llamador cae al modo manual (escribir el ID).
    """
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
    resp = client.models.list()
    return sorted({m.id for m in resp.data})


@dataclass(frozen=True)
class AIConfig:
    api_key: str
    base_url: str
    model: str
    temperature: float = 0.3
    timeout: float = 120.0


class OpenAICompatibleProvider(AIProvider):
    def __init__(self, config: AIConfig) -> None:
        # Import perezoso: si no usás IA, no obligamos a tener openai instalado.
        from openai import OpenAI

        self._config = config
        self._client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
        )

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._config.model,
            temperature=self._config.temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = resp.choices[0].message.content
        return content or ""
