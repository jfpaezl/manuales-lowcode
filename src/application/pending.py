"""Detección y relleno de huecos [COMPLETAR] en un manual.

Texto puro, SIN IA: encontrar los huecos y reemplazarlos por las respuestas
es determinístico y fiel. La IA solo se usa (aparte) para REDACTAR la pregunta
de cada hueco; el relleno final lo hace este módulo, exacto.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_MARKER = "[COMPLETAR]"
_MARKER_RE = re.compile(r"\[COMPLETAR\]")
# Numeración o viñeta al inicio de una línea: "1. ", "2) ", "- ", "* ", "• ".
_BULLET_RE = re.compile(r"^\s*(?:\d+[.\)]|[-*•])\s*")


@dataclass
class PendingSlot:
    """Un hueco [COMPLETAR] y su contexto (para que la IA arme la pregunta)."""
    section: str   # la sección (encabezado ##) donde aparece
    line: str      # la línea donde aparece


def find_pending(markdown: str) -> list[PendingSlot]:
    """Encuentra cada [COMPLETAR] en orden de documento, con su sección."""
    slots: list[PendingSlot] = []
    section = ""
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            section = stripped.lstrip("#").strip()
        for _ in range(stripped.count(_MARKER)):
            slots.append(PendingSlot(section=section, line=stripped))
    return slots


def fill_pending(markdown: str, answers: list[str]) -> str:
    """Reemplaza el i-ésimo [COMPLETAR] por answers[i].

    Respuesta vacía (o si faltan respuestas) → deja el hueco intacto. Es exacto:
    no toca nada más del manual."""
    pendientes = iter(answers)

    def repl(match: re.Match) -> str:
        try:
            answer = next(pendientes)
        except StopIteration:
            return match.group(0)
        answer = (answer or "").strip()
        return answer or match.group(0)

    return _MARKER_RE.sub(repl, markdown)


def parse_questions(raw: str, count: int) -> list[str]:
    """Convierte la respuesta de la IA en EXACTAMENTE `count` preguntas, en orden.

    Limpia numeración/viñetas. Si faltan, rellena con un genérico; si sobran, trunca.
    Así el mapeo pregunta[i] ↔ hueco[i] siempre se mantiene."""
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    questions = [_BULLET_RE.sub("", line) for line in lines][:count]
    while len(questions) < count:
        questions.append("Completá este dato faltante:")
    return questions
