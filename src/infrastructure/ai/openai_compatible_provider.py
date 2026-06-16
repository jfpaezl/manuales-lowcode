"""Adaptador de IA: cliente OpenAI-compatible.

UNA sola clase sirve para OpenCode Go, OpenRouter, Ollama, Groq... todos
hablan el mismo protocolo. Cambiás base_url + model en config.toml y listo.
Esa es la magia de programar contra un estándar y no contra un proveedor.
"""
from __future__ import annotations

from dataclasses import dataclass

from ...domain.ports import AIAuthError, AIProvider


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
    # 300s (5 min): modelos lentos/pesados (ej minimax) pasan los 120s, sobre todo
    # en la integración final de una Solution (prompt grande). Configurable en config.toml.
    timeout: float = 300.0
    # El SDK de OpenAI reintenta 2 veces por defecto: en una Solution de N
    # componentes, una llamada lenta tardaría hasta 3×timeout antes de fallar,
    # multiplicado por N → cuelgues larguísimos. Lo acotamos a 1 reintento.
    max_retries: int = 1


class OpenAICompatibleProvider(AIProvider):
    def __init__(self, config: AIConfig) -> None:
        # Import perezoso: si no usás IA, no obligamos a tener openai instalado.
        from openai import OpenAI

        self._config = config
        self._client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            resp = self._create(messages, temperature=self._config.temperature)
        except AIAuthError:
            raise
        except Exception as exc:  # noqa: BLE001 — algunos modelos rechazan la temperature
            if not _is_temperature_rejection(exc):
                raise
            # Modelos como Kimi/Moonshot solo aceptan temperature=1: la app es
            # "OpenAI-compatible, cambiás el modelo y listo", así que NO nos rompemos
            # por la política de UN modelo. Reintentamos omitiendo la temperatura y
            # dejamos que el modelo use su default.
            resp = self._create(messages)
        content = resp.choices[0].message.content
        return content or ""

    def _create(self, messages, *, temperature: float | None = None):
        """Una llamada al endpoint. `temperature=None` la omite (default del modelo).
        Centraliza el mapeo del 401 a AIAuthError para ambos intentos."""
        kwargs = {"model": self._config.model, "messages": messages}
        if temperature is not None:
            kwargs["temperature"] = temperature
        try:
            return self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 — distinguimos el 401 (auth) del resto
            if getattr(exc, "status_code", None) == 401 or \
                    exc.__class__.__name__ == "AuthenticationError":
                raise AIAuthError(
                    f"401 no autorizado para el modelo «{self._config.model}». "
                    "Revisá que el modelo exista en tu conexión y que la API key tenga "
                    "acceso, o dejá el modelo obrero vacío para usar el principal."
                ) from exc
            raise


def _is_temperature_rejection(exc: Exception) -> bool:
    """¿El endpoint rechazó la request por la temperatura? (400 + mención de
    'temperature'). Algunos modelos solo admiten un valor fijo (ej. Kimi: solo 1)."""
    status = getattr(exc, "status_code", None)
    if status not in (400, None):  # None: proveedores que no exponen status_code
        return False
    return "temperature" in str(exc).lower()
