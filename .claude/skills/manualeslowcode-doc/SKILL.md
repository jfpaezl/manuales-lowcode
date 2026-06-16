---
name: manualeslowcode-doc
description: >
  Cómo funciona el motor de documentación low-code (extractores, knowledge packs,
  generación orquestador/obrero, seguimiento de cambios) de ManualesLowcode.
  Trigger: Al extender extractores, prompts de IA, knowledge packs o el diff entre
  versiones; al sumar soporte de una tecnología (Power Platform, Dataverse, VBA).
license: Apache-2.0
metadata:
  author: gentleman-programming
  version: "1.0"
---

## When to Use

- Sumar/ajustar un extractor de paquetes (Power Automate, Power Apps, Dataverse, VBA).
- Tocar cómo la IA redacta los manuales (prompts) o qué conocimiento de dominio usa.
- Trabajar el seguimiento de cambios entre versiones (deprecación/diff).
- Documentar una tecnología nueva: extractor + knowledge pack + tests.

## Arquitectura (hexagonal — respetar las capas)

| Capa | Carpeta | Regla |
|------|---------|-------|
| Dominio | `src/domain/` | Python puro. NO importa PyQt/SQLite/IA. Entidades, puertos, `change_tracking`. |
| Aplicación | `src/application/` | Casos de uso. `manual_service.py` (orquesta), `ai_prompts.py` (qué se le pide a la IA), `knowledge/` (qué cubrir por tecnología). |
| Infraestructura | `src/infrastructure/` | Adaptadores: `extractors/`, `*_repository.py`, `pdf/`, `ai/`. |
| Presentación | `src/presentation/` | PyQt. Habla SOLO con `ManualService`. |

La UI nunca toca repos/IA directo. El dominio nunca importa hacia afuera.

## Critical Patterns

- **Extraer ≠ redactar.** El extractor produce un `ExtractedPackage` con la estructura
  FIEL (verdad verificable). La IA la redacta (interpretación). No mezclar.
- **`kind` manda.** Cada `ExtractedPackage` tiene un `kind` (`power-automate-flow`,
  `power-apps-canvas`, `excel-vba`, `dataverse-table`, `dataverse-security`,
  `power-platform-solution`). El `kind` enrutea el knowledge pack y la etiqueta del worker.
- **Funcional = breve / Técnico = detalle.** `_nivel_detalle(tipo)` lo gobierna. Los
  knowledge packs se inyectan SOLO en TÉCNICO (`_knowledge_block(kind, tipo)`). No metas
  detalle técnico (columnas, orden de ejecución) en el funcional.
- **Orquestador/obrero.** Paquete con >1 componente (Solution) → obrero (modelo chico)
  redacta cada componente, orquestador (modelo potente) integra siguiendo `_ESTRUCTURA`.
  Atómico → una sola llamada (`build_from_package`).
- **Identidad estable para el diff.** `ExtractedPackage.unique_name` (UniqueName de
  Dataverse para Solutions; `name` para atómicos). `fingerprint` = sha256 del
  `summary_markdown`. El diff (`change_tracking.diff_package`) compara por nombre de
  componente; fingerprint distinto = MODIFICADO.

## Cómo sumar un extractor

1. Crear `src/infrastructure/extractors/{tech}.py`. Si NO es un ZIP propio (vive dentro
   de una Solution, como Dataverse), exponé un método que reciba el contenido y devuelva
   `list[ExtractedPackage]` + warnings; lo invoca `SolutionExtractor` por composición.
2. Setear en cada `ExtractedPackage`: `kind`, `name`, `summary_markdown`, `unique_name`
   (identidad estable), y `warnings` ante lo no legible (DEFENSIVO, no romper).
3. Si es un ZIP propio, implementar `PackageExtractor` (`supports` + `extract`) y
   registrarlo en `dispatcher.py` (OJO el orden: Solution primero, contiene .msapp).
4. Agregar el knowledge pack del nuevo `kind` (ver abajo) y la etiqueta en
   `ai_prompts._KIND_LABEL`.
5. Tests con XML/ZIP sintético del formato real.

## Cómo sumar un knowledge pack

- Crear `src/application/knowledge/{tech}.py` con `GUIDANCE = {"<kind>": "<qué cubrir>"}`.
- Registrarlo en `src/application/knowledge/__init__.py` (lista `_mod`).
- La guía es QUÉ documentar (columnas, claves, permisos), NO el nivel de detalle
  (eso lo maneja `_nivel_detalle`). Se inyecta solo en el manual técnico.
- Si el `kind`/categoría son nuevos, sumá la categoría (con su keyword en el hint)
  en `db.py` (`_DEFAULT_CATEGORIES` + `_KNOWLEDGE_CATEGORIES`) y, opcional, señales
  de contenido en `_CONTENT_SIGNALS`.

## Ruteo del pack — SALVAGUARDA en cascada

`ai_prompts._resolve_knowledge(kind=, categoria_hint=, content=)` resuelve el pack
probando, en orden de fiabilidad: **kind** (estructura extraída) → **categoría**
(hint elegido) → **contenido** (`knowledge_for_text`: detecta la tecnología leyendo
el material real). Así, independientemente de la categoría, se rutea a lo que de
verdad se documenta. En una Solution cada componente se documenta por SU kind, no
por la categoría de la solución.

## Seguimiento de cambios (deprecación entre versiones)

- `package_snapshots` (SQLite, PK `unique_name`) guarda la foto de la última importación.
- Al re-importar: `ManualService.diff_for(extracted)` compara contra la foto →
  `DiffResult` (deprecated/modified/added). Se pasa a los prompts (`_cambios`) que marcan
  ⚠/🔄/🆕 y agregan la sección de cambios + la fila de versión en Versionamiento.
- El snapshot se guarda al terminar la importación, ligado a los ids de los manuales
  funcional y técnico (para actualizarlos como nueva versión, no crear otros).

## Commands

```bash
# Tests (siempre con el venv del proyecto)
.venv/Scripts/python.exe -m pytest tests/ -q

# Un módulo puntual
.venv/Scripts/python.exe -m pytest tests/test_solution_extractor.py -q

# Chequear que un archivo compila (UI no testeada)
.venv/Scripts/python.exe -m py_compile src/presentation/main_window.py
```

## Resources

- Formatos y lógica de extracción: `src/infrastructure/extractors/`
- Prompts y orquestación: `src/application/ai_prompts.py`, `manual_service.py`
- Diff entre versiones: `src/domain/change_tracking.py`
