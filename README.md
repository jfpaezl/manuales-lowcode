# Manuales Low-Code

App de escritorio (PyQt6 + SQLite) para crear **manuales funcionales y técnicos**
de desarrollo low-code (Power Apps, macros, Python). Genera **PDF versionado** y
guarda todo —incluido el PDF— dentro de un único archivo SQLite. Tiene un
**asistente de IA** que se conecta a OpenCode Go (o cualquier endpoint
OpenAI-compatible) para generar manuales, documentar código o convertir
transcripciones en documentación.

## Arquitectura (hexagonal)

```
src/
├── domain/          Entidades + puertos (interfaces). Python puro, sin dependencias.
├── application/     ManualService (casos de uso) + prompts de IA.
├── infrastructure/  Adaptadores: SQLite, WeasyPrint (PDF), IA OpenAI-compatible.
└── presentation/    UI de PyQt6.
main.py              Composition root: cablea todo. Único lugar con dependencias concretas.
```

El dominio no sabe que existen SQLite, WeasyPrint ni OpenCode. Cambiar cualquier
detalle (motor de PDF, proveedor de IA, base de datos) se hace en `main.py`.

## Instalación

### 1. Dependencias de Python

```bash
pip install -r requirements.txt
```

### 2. GTK / Pango (necesario para el PDF en Windows)

WeasyPrint usa librerías nativas que NO vienen con pip. En Windows:

```bash
winget install --id tschoonj.GTKForWindows -e
```

> **Importante:** después de instalar GTK, **cerrá y reabrí la terminal** para que
> se recargue el PATH. Si no, WeasyPrint tira `cannot load library libgobject`.

### 3. Configuración de IA (opcional)

```bash
cp config.example.toml config.toml
```

Editá `config.toml` con tu API key de OpenCode Go:

```toml
[ai]
api_key  = "tu-api-key-de-opencode-go"
base_url = "https://opencode.ai/zen/v1"
model    = "glm-5.1"
```

La app funciona sin IA (solo no aparece el asistente).

## Uso

```bash
python main.py
```

1. **➕ Nuevo** → creás un manual (título, tipo, categoría).
2. Escribís el contenido en **Markdown**, o lo generás con el **asistente de IA**.
3. **💾 Guardar versión + PDF** → crea una versión nueva, genera el PDF y lo guarda.
4. Pestaña **📄 Vista PDF** → previsualizás el resultado real.
5. Pestaña **🕑 Versiones** → historial completo; doble clic para ver cualquier versión.

## Tests

```bash
python -m pytest -q
```

Los tests cubren dominio, persistencia y casos de uso con dobles de prueba
(no necesitan GTK ni conexión a IA).
