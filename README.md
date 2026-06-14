# Manuales Low-Code

Aplicación de escritorio (PyQt6) para generar **manuales técnicos y funcionales**
de soluciones low-code con ayuda de IA. Pensada para documentar automatizaciones
y desarrollos de **Power Automate, Power Apps, Solutions de Power Platform y macros
VBA de Excel**, además de código pegado a mano (Python, VBA, Power Fx, etc.).

Genera **PDF versionado** con tu identidad de marca y guarda todo —incluidos los
PDFs— dentro de un único archivo SQLite. El **asistente de IA** se conecta a
cualquier proveedor OpenAI-compatible (OpenCode, OpenAI, Anthropic, Google,
OpenRouter, Ollama) para redactar, documentar, integrar y completar manuales.

---

## Tabla de contenidos

- [Características](#características)
- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Configuración de la IA](#configuración-de-la-ia)
- [Uso](#uso)
  - [Crear y gestionar manuales](#crear-y-gestionar-manuales)
  - [El asistente de IA](#el-asistente-de-ia)
  - [Importar paquetes (Power Platform / Excel)](#importar-paquetes-power-platform--excel)
  - [Completar pendientes](#completar-pendientes)
  - [Datos del documento](#datos-del-documento)
  - [Identidad del PDF (marca, lema, logo)](#identidad-del-pdf-marca-lema-logo)
  - [Versiones y exportación](#versiones-y-exportación)
  - [Atajos de teclado](#atajos-de-teclado)
- [Cómo funciona la generación](#cómo-funciona-la-generación)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Tests](#tests)
- [Privacidad y seguridad](#privacidad-y-seguridad)
- [Solución de problemas](#solución-de-problemas)
- [Licencia](#licencia)

---

## Características

- 📝 **Editor Markdown** con vista previa del PDF real.
- 🤖 **Asistente de IA** con 4 modos: generar desde cero, documentar código,
  transcripción → manual, y complementar un manual existente.
- 📦 **Importación de paquetes**: extrae la lógica real de
  - **Power Automate** (flujo exportado individual),
  - **Power Apps** (canvas app `.msapp`),
  - **Solutions** de Power Platform (con flujos + apps adentro),
  - **macros VBA de Excel** (`.xlsm`).
- ✅ **Completar pendientes**: la IA te pregunta por cada hueco `[COMPLETAR]` y
  vos respondés; los huecos se rellenan con tus respuestas exactas.
- 🏢 **Identidad de marca configurable**: nombre, lema y logo en la portada.
- 🧠 **Generación orquestador/obrero**: para paquetes grandes, un modelo potente
  coordina y un modelo barato redacta cada componente (ahorra costo).
- 🗂️ **Versionado**: cada guardado crea una versión inmutable con su PDF.
- 🎨 **Tema visual** coherente con la marca del PDF.
- 🔌 **Multi-proveedor de IA** OpenAI-compatible, con listado de modelos por conexión.
- 💾 **Todo en un SQLite**: manuales, versiones y PDFs en un solo archivo.

---

## Requisitos

- **Python 3.11 o superior** (usa `tomllib` de la stdlib).
- **GTK/Pango** instalado aparte (lo necesita WeasyPrint para generar PDFs).
- **Una API key** de algún proveedor OpenAI-compatible (opcional: la app corre
  sin IA, solo que el asistente queda deshabilitado).

---

## Instalación

### 1. Cloná el repositorio

```bash
git clone https://github.com/jfpaezl/manuales-lowcode.git
cd manuales-lowcode
```

### 2. Creá un entorno virtual e instalá las dependencias

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

pip install -r requirements.txt
```

Dependencias principales: `PyQt6`, `weasyprint`, `Jinja2`, `markdown`, `openai`,
`PyYAML` (Power Apps), `oletools` (macros VBA), `pytest`.

### 3. Instalá GTK / Pango (necesario para el PDF)

WeasyPrint usa librerías nativas que **no** vienen con pip.

**Windows:**

```bash
winget install --id tschoonj.GTKForWindows -e
```

> ⚠️ **Importante:** después de instalar GTK, **cerrá y reabrí la terminal** para
> que se recargue el PATH. Si no, WeasyPrint tira `cannot load library libgobject`.

**Linux (Debian/Ubuntu):**

```bash
sudo apt install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 libffi-dev
```

**macOS:**

```bash
brew install pango gdk-pixbuf libffi
```

> La app **funciona sin GTK** para todo lo que no sea generar el PDF: podés crear
> manuales y guardarlos sin PDF. Solo la generación del PDF requiere GTK.

### 4. (Opcional) Configurá la IA

Copiá el archivo de ejemplo y completá tus datos:

```bash
cp config.example.toml config.toml
```

También podés configurar la IA **desde la app** (menú ⚙ Configuración → Conexión
de IA…), sin tocar archivos. Ver la sección siguiente.

### 5. Ejecutá la app

```bash
python main.py
```

---

## Configuración de la IA

La app habla **protocolo OpenAI-compatible**, así que sirve con muchos
proveedores. Desde **⚙ Configuración → Conexión de IA…** elegís un preset y pegás
tu API key:

| Proveedor | Base URL | Notas |
|-----------|----------|-------|
| OpenCode Go | `https://opencode.ai/zen/go/v1` | El `/go/` va en el medio |
| OpenCode Zen | `https://opencode.ai/zen/v1` | |
| OpenAI | `https://api.openai.com/v1` | Nativo |
| Anthropic (Claude) | `https://api.anthropic.com/v1/` | Capa de compatibilidad |
| Google (Gemini) | `https://generativelanguage.googleapis.com/v1beta/openai/` | Capa de compatibilidad |
| OpenRouter | `https://openrouter.ai/api/v1` | |
| Ollama (local) | `http://localhost:11434/v1` | API key cualquiera |

**Cargar modelos disponibles:** una vez puesta la API key, tocá
**🔄 Cargar modelos disponibles** y la app consulta a la conexión qué modelos
ofrece y los lista. Si el proveedor no soporta el listado, escribís el ID a mano.

**Modelo orquestador + modelo obrero (opcional):** para generar paquetes grandes
(Solutions con muchos componentes), podés configurar un **modelo obrero** más
barato. El **modelo principal** coordina y el **obrero** redacta cada componente.
Si dejás el obrero vacío, se usa el principal para todo.

> ℹ️ Anthropic y Google funcionan vía su **capa de compatibilidad OpenAI**, que
> cubre lo que esta app necesita (chat). Los IDs de modelo cambian seguido: si uno
> falla, verificá el nombre exacto en tu proveedor.

El `config.toml` resultante se ve así:

```toml
[ai]
api_key      = "tu-api-key"
base_url     = "https://opencode.ai/zen/go/v1"
model        = "glm-5.1"
worker_model = ""              # opcional: modelo "obrero" (chico)

[storage]
db_path = "manuales.db"

[user]
name = "Tu Nombre"            # responsable/autor por defecto
area = "Tu Área"

[brand]
name    = "Mi Empresa"        # marca de la portada del PDF
tagline = "Documentación interna"
logo    = ""                  # ruta a un PNG/JPG (opcional)
```

---

## Uso

### Crear y gestionar manuales

- **➕ Nuevo** — crea un manual (título, tipo *funcional* o *técnico*, categoría,
  descripción).
- **✏ Renombrar** — cambia el título. *Nota:* no reescribe los PDFs ya generados
  (las versiones son inmutables); el título nuevo se usa en las versiones futuras.
- **🗑 Eliminar** — borra el manual y todas sus versiones.

El contenido se escribe en **Markdown** y se previsualiza como PDF real.

### El asistente de IA

En la caja **Asistente de IA** elegís un modo (el cuadro de texto te guía según
el modo elegido) y tocás **✨ Generar con IA**:

| Modo | Qué hace | Qué poner en el cuadro |
|------|----------|------------------------|
| **Generar manual desde cero** | Redacta un manual completo sobre un tema | El tema u objeto a documentar |
| **Documentar código pegado** | Documenta código fuente | El código (VBA, Power Fx, Python…) |
| **Transcripción → manual** | Convierte una explicación hablada en manual | La transcripción |
| **Complementar manual actual** | Integra info nueva en el manual del editor | Qué agregar o corregir |

Los modos *Generar* y *Transcripción* abren un diálogo para los **datos del
documento** (responsable, área, fecha). *Complementar* reemplaza el editor con la
versión integrada; los demás agregan el resultado abajo.

### Importar paquetes (Power Platform / Excel)

Tocá **📦 Importar** y elegí un archivo. La app detecta el formato, extrae la
lógica real y la IA la redacta como manual.

| Formato | Archivo | Cómo exportarlo |
|---------|---------|-----------------|
| **Power Automate** (flujo) | `.zip` | Power Automate → *Mis flujos* → ⋯ → **Exportar → Paquete (.zip)** |
| **Power Apps** (canvas) | `.msapp` o `.zip` | Power Apps Studio → **Archivo → Guardar como → Este equipo**, o *Exportar paquete* |
| **Solution** (Power Platform) | `.zip` | make.powerapps.com → *Soluciones* → **Exportar solución** |
| **Macros de Excel** | `.xlsm` | El propio archivo de Excel con macros |

> La extracción es **determinística** (código, sin IA): lo que sale es fiel a tu
> paquete. La IA solo lo redacta, con instrucción de **no inventar**.

### Completar pendientes

Cuando un manual tiene huecos marcados con `[COMPLETAR]`, tocá
**✅ Completar pendientes**: la IA arma una pregunta por cada hueco, vos respondés
en un diálogo, y los huecos se rellenan **con tus respuestas exactas** (lo que
dejes vacío queda como `[COMPLETAR]`).

### Datos del documento

Para manuales **funcionales**, la sección «Datos generales» se llena con datos
reales que aportás vos (responsable, área, fecha) — la IA no los inventa. El
responsable y el área se recuerdan; la fecha viene precargada con hoy y es editable.

### Identidad del PDF (marca, lema, logo)

En **⚙ Configuración → Identidad del documento…** configurás lo que aparece en la
**portada** de los PDF:

- **Marca / Empresa** — el nombre arriba en la portada.
- **Lema (tagline)** — un subtítulo opcional.
- **Logo** — una imagen PNG/JPG que se incrusta en el PDF.

> El logo se guarda por **ruta** y se incrusta al generar. Si movés o borrás el
> archivo, el logo se omite (sin romper el PDF) y lo volvés a elegir.

### Versiones y exportación

- **💾 Guardar versión + PDF** — crea una versión inmutable y genera su PDF.
- Pestaña **📄 Vista PDF** — previsualización del PDF real.
- Pestaña **🕑 Versiones** — historial; doble clic para ver cualquier versión.
- **⬇ Exportar PDF a disco…** — guarda el PDF de la última versión a un archivo.

### Atajos de teclado

| Atajo | Acción |
|-------|--------|
| `Ctrl + N` | Nuevo manual |
| `Ctrl + S` | Guardar versión + PDF |
| `F2` | Renombrar manual |
| `Supr` | Eliminar (con la lista de manuales enfocada) |

---

## Cómo funciona la generación

El principio de diseño es **separar extraer de redactar**:

1. **Extraer** (código, sin IA): al importar un paquete, el código lee el ZIP y
   reconstruye la lógica real (trigger y acciones de un flujo, jerarquía de
   controles de una app, módulos VBA…). Esto es **verdad verificable**.
2. **Redactar** (IA): la estructura extraída se le pasa a la IA, con instrucción
   explícita de **respetarla y no inventar**. Lo que falte queda en `[COMPLETAR]`.

Para **paquetes grandes** (Solutions), entra el patrón **orquestador/obrero**: el
modelo *obrero* (barato) redacta cada componente por separado y el modelo
*orquestador* (potente) integra todo en un manual coherente. Así el grueso del
trabajo lo hace el modelo barato.

---

## Estructura del proyecto

Arquitectura **hexagonal** (ports & adapters): el dominio no conoce SQLite,
WeasyPrint ni los proveedores de IA. Todo se cablea en `main.py`.

```
manuales-lowcode/
├── main.py                      Composition root: cablea todo
├── requirements.txt
├── config.example.toml
└── src/
    ├── config.py                Carga/guarda config.toml
    ├── domain/                  Python puro, sin dependencias
    │   ├── entities.py          Manual, ManualVersion, ExtractedPackage…
    │   └── ports.py             Interfaces (repos, PDF, IA, extractor)
    ├── application/
    │   ├── manual_service.py    Casos de uso
    │   ├── ai_prompts.py        Prompts de la IA
    │   └── pending.py           Detección/relleno de [COMPLETAR]
    ├── infrastructure/
    │   ├── ai/                  Proveedor OpenAI-compatible
    │   ├── pdf/                 WeasyPrint + plantillas (HTML/CSS) + fuentes
    │   ├── extractors/          Dispatcher + Power Automate / Power Apps / Solution / Excel VBA
    │   ├── manual_repository.py SQLite
    │   ├── category_repository.py
    │   └── db.py
    └── presentation/            UI de PyQt6 (ventana, diálogos, tema)
```

---

## Tests

```bash
python -m pytest -q
```

Cubren dominio, persistencia, casos de uso, extractores y prompts con dobles de
prueba. **No necesitan GTK ni conexión a IA.**

---

## Privacidad y seguridad

- Tu **API key** vive en `config.toml`, que está en `.gitignore` y **nunca se sube**.
- Tu base de datos (`manuales.db`, con manuales y PDFs) también está ignorada.
- Todo el procesamiento de paquetes es **local**; solo la redacción con IA envía
  texto al proveedor que configures.

> Si vas a publicar un fork, revisá que no queden datos ni marcas internas en el
> código antes de hacerlo público.

---

## Solución de problemas

| Síntoma | Causa / solución |
|---------|------------------|
| `cannot load library libgobject…` al generar PDF | Falta GTK o el PATH no se recargó. Instalá GTK y **reabrí la terminal**. |
| El asistente de IA aparece deshabilitado | No hay IA configurada. ⚙ Configuración → Conexión de IA…. |
| Anthropic da error pidiendo `max_tokens` | Su capa de compatibilidad puede requerirlo; reportalo y se agrega el parámetro. |
| «Cargar modelos» no trae nada | El proveedor no expone `/models`. Escribí el ID del modelo a mano. |
| El manual sale cortado en Solutions grandes | Configurá un **modelo obrero** para repartir el trabajo, o importá componente por componente. |
| El logo no aparece en el PDF | La ruta del logo cambió. Reelegí el archivo en Identidad del documento. |

---

## Licencia

[MIT](LICENSE) — uso libre con atribución.
