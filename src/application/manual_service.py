"""ManualService: el caso de uso. Orquesta dominio, persistencia, PDF e IA.

La UI (PyQt) habla SOLO con este servicio. Nunca toca el repo, el renderer
ni la IA directamente. Si mañana cambiás de UI, este servicio no se entera.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date

from ..domain.change_tracking import (
    DiffResult, PackageSnapshot, StoredSnapshot, diff_package,
)
from ..domain.entities import (
    Category, ExtractedPackage, Manual, ManualType, ManualVersion, Section,
)
from ..domain.ports import (
    AIAuthError, AIProvider, CategoryRepository, DocxRenderer, ManualRepository,
    PackageExtractor, PackageSnapshotRepository, PDFRenderer,
)
from . import ai_prompts, pending


def _default_md_to_html(text: str) -> str:
    """Convierte Markdown a HTML. Aislado para poder mockearlo en tests."""
    import markdown  # import perezoso: el dominio no depende de esto

    return markdown.markdown(text, extensions=["fenced_code", "tables", "toc"])


class ManualService:
    def __init__(
        self,
        repo: ManualRepository,
        renderer: PDFRenderer | None = None,
        ai: AIProvider | None = None,
        md_to_html: Callable[[str], str] = _default_md_to_html,
        categories: CategoryRepository | None = None,
        extractor: PackageExtractor | None = None,
        worker_ai: AIProvider | None = None,
        snapshots: PackageSnapshotRepository | None = None,
        docx_renderer: DocxRenderer | None = None,
    ) -> None:
        self._repo = repo
        self._renderer = renderer
        self._docx = docx_renderer
        self._ai = ai
        self._md_to_html = md_to_html
        self._categories = categories
        self._extractor = extractor
        # "Obrero": modelo chico para la generación orquestada. Si no hay, se usa
        # el orquestador (self._ai) para todo (degrada con elegancia).
        self._worker_ai = worker_ai
        # Memoria de paquetes importados, para el seguimiento de cambios entre versiones.
        self._snapshots = snapshots

    # --- IA: configuración en caliente ------------------------------------

    @property
    def ai_ready(self) -> bool:
        return self._ai is not None

    @property
    def ai_model_name(self) -> str:
        """Nombre del modelo principal (para mostrarlo en los logs de la UI). "" si
        el proveedor no lo expone o no hay IA."""
        return getattr(self._ai, "model", "") if self._ai is not None else ""

    def set_ai(self, provider: AIProvider | None) -> None:
        """Cambia el proveedor de IA (orquestador) sin reiniciar la app."""
        self._ai = provider

    def set_worker_ai(self, provider: AIProvider | None) -> None:
        """Cambia el proveedor 'obrero' (modelo chico) sin reiniciar la app."""
        self._worker_ai = provider

    # --- CRUD de manuales -------------------------------------------------

    def create_manual(
        self, title: str, tipo: ManualType, categoria: str, description: str = ""
    ) -> Manual:
        return self._repo.add(
            Manual(title=title, type=tipo, category=categoria, description=description)
        )

    def list_manuals(self) -> list[Manual]:
        return self._repo.list()

    def get_manual(self, manual_id: int) -> Manual | None:
        return self._repo.get(manual_id)

    def rename_manual(self, manual_id: int, new_title: str) -> None:
        """Cambia el título de un manual. El título nuevo se usa en las versiones
        que generes a partir de ahora; los PDFs ya hechos no se tocan."""
        new_title = new_title.strip()
        if not new_title:
            raise ValueError("El título no puede estar vacío")
        self._repo.rename(manual_id, new_title)

    def delete_manual(self, manual_id: int) -> None:
        self._repo.delete(manual_id)

    # --- Categorías (catálogo editable) -----------------------------------

    def list_categories(self) -> list[Category]:
        return self._categories.list() if self._categories else []

    def add_category(self, label: str, ai_hint: str = "") -> Category:
        if not self._categories:
            raise RuntimeError("No hay catálogo de categorías configurado")
        return self._categories.add(Category(label=label.strip(), ai_hint=ai_hint.strip()))

    def rename_category(self, old_label: str, new_label: str, ai_hint: str | None = None) -> None:
        """Renombra la categoría Y reapunta todos los manuales que la usan."""
        if not self._categories:
            raise RuntimeError("No hay catálogo de categorías configurado")
        new_label = new_label.strip()
        self._categories.rename(old_label, new_label, ai_hint)
        if new_label != old_label:
            self._repo.reassign_category(old_label, new_label)

    def delete_category(self, label: str) -> None:
        """Borra una categoría solo si NINGÚN manual la usa (borrado seguro)."""
        if not self._categories:
            raise RuntimeError("No hay catálogo de categorías configurado")
        en_uso = self._repo.count_by_category(label)
        if en_uso > 0:
            raise ValueError(
                f"No se puede borrar '{label}': {en_uso} manual(es) la usan. "
                "Reasignalos primero."
            )
        self._categories.delete(label)

    # --- Versionado + PDF -------------------------------------------------

    def save_version(
        self,
        manual_id: int,
        sections: Sequence[Section],
        change_note: str = "",
        generate_pdf: bool = True,
    ) -> ManualVersion:
        """Crea una versión nueva (inmutable), genera su PDF y la persiste.

        generate_pdf=False permite guardar sin PDF (ej: si GTH/WeasyPrint
        todavía no está instalado). El manual no se pierde.
        """
        manual = self._repo.get(manual_id)
        if manual is None:
            raise ValueError(f"No existe el manual {manual_id}")

        sections = list(sections)
        version = ManualVersion(
            version=manual.next_version_number(),
            content_html=self._combine(sections),
            sections=sections,
            change_note=change_note,
        )
        if self._renderer is not None and generate_pdf:
            version.pdf_blob = self._renderer.render(manual, version)
        return self._repo.add_version(manual_id, version)

    def get_version_pdf(self, version_id: int) -> bytes | None:
        version = self._repo.get_version(version_id)
        return version.pdf_blob if version else None

    @property
    def docx_ready(self) -> bool:
        return self._docx is not None

    def build_docx(self, manual: Manual, version: ManualVersion) -> bytes:
        """Genera el .docx de una versión AL VUELO (no se guarda como BLOB: el Word
        es editable, se regenera cuando lo pedís). NO toca la base ni la red."""
        if self._docx is None:
            raise RuntimeError("No hay renderer de Word configurado")
        return self._docx.render(manual, version)

    @staticmethod
    def _combine(sections: Sequence[Section]) -> str:
        """Une las secciones en un único HTML de cuerpo, respetando el orden."""
        ordered = sorted(sections, key=lambda s: s.order)
        parts = []
        for s in ordered:
            heading = f"<h2>{s.title}</h2>\n" if s.title.strip() else ""
            parts.append(f"<section>{heading}{s.content_html}</section>")
        return "\n".join(parts)

    # --- IA: los 3 modos --------------------------------------------------

    def category_hint(self, categoria: str) -> str:
        """Resuelve la descripción (ai_hint) de una categoría.

        Toca la base, así que SE LLAMA EN EL HILO PRINCIPAL (no en el worker
        de IA). El resultado ya resuelto se le pasa a los métodos ai_*.
        """
        return self._categories.get_hint(categoria) if self._categories else categoria

    @staticmethod
    def _fecha_o_hoy(fecha: str) -> str:
        """La fecha que mandó la UI (editable) o, si vino vacía, la de hoy."""
        return fecha.strip() or date.today().strftime("%d/%m/%Y")

    def ai_generate(
        self, *, topic: str, tipo: ManualType, categoria_hint: str, author: str = "",
        context: str = "", area: str = "", fecha: str = "", developer: str = "",
    ) -> str:
        """Modo 1 → devuelve Markdown. NO toca la base: seguro en otro hilo."""
        system, user = ai_prompts.build_generate(
            topic=topic, tipo=tipo, categoria_hint=categoria_hint,
            author=author, fecha=self._fecha_o_hoy(fecha), context=context, area=area,
            developer=developer,
        )
        return self._ask_ai(system, user)

    def ai_document_code(
        self, *, code: str, tipo: ManualType, categoria_hint: str, language_hint: str = ""
    ) -> str:
        """Modo 2 → documenta código pegado. NO toca la base."""
        system, user = ai_prompts.build_document_code(
            code=code, tipo=tipo, categoria_hint=categoria_hint, language_hint=language_hint
        )
        return self._ask_ai(system, user)

    @property
    def extractor_ready(self) -> bool:
        return self._extractor is not None

    def extract_package(self, data: bytes, filename: str = "") -> ExtractedPackage:
        """Lee un ZIP exportado (ej: flujo de Power Automate) y devuelve su
        estructura. NO toca la base ni la red: seguro en cualquier hilo."""
        if self._extractor is None:
            raise RuntimeError("No hay extractor de paquetes configurado")
        return self._extractor.extract(data, filename)

    def ai_from_package(
        self, *, extracted: ExtractedPackage, tipo: ManualType, categoria_hint: str,
        author: str = "", area: str = "", fecha: str = "", developer: str = "",
        diff: DiffResult | None = None, progress: Callable[[str], None] | None = None,
    ) -> str:
        """Modo 4 → de la estructura extraída de un paquete a manual. NO toca la base.

        Si el paquete trae VARIOS componentes (ej: una Solution), usa el patrón
        orquestador/obrero: el modelo chico redacta cada componente, el potente
        integra. Si es atómico, una sola llamada. `diff` (opcional) marca los
        cambios respecto a la versión anterior. `progress` (opcional) reporta el
        avance componente a componente para que la UI no parezca colgada."""
        if len(extracted.components) > 1:
            return self._orchestrate(
                extracted, tipo, categoria_hint, author, area, fecha, developer, diff,
                progress,
            )
        if progress:
            progress("Generando el manual…")
        system, user = ai_prompts.build_from_package(
            package_name=extracted.name, package_summary=extracted.summary_markdown,
            tipo=tipo, categoria_hint=categoria_hint,
            author=author, fecha=self._fecha_o_hoy(fecha), area=area, developer=developer,
            version=extracted.version, diff=diff, kind=extracted.kind,
        )
        return self._ask_ai(system, user)

    def _section_provider(self, tipo: ManualType) -> AIProvider:
        """Qué modelo redacta cada sección de componente en una Solution.

        - FUNCIONAL → el ORQUESTADOR (modelo potente/estable). Sus secciones son
          BREVES, así que el costo extra es bajo y se evita que el obrero (chico)
          se cuelgue con manuales grandes.
        - TÉCNICO → el OBRERO (modelo chico) para el grueso; si no hay, degrada al
          orquestador. Acá es donde el ahorro del obrero importa (secciones largas)."""
        if tipo is ManualType.FUNCIONAL:
            return self._ai
        return self._worker_ai or self._ai

    def _orchestrate(
        self, extracted: ExtractedPackage, tipo: ManualType, categoria_hint: str,
        author: str, area: str, fecha: str, developer: str = "",
        diff: DiffResult | None = None, progress: Callable[[str], None] | None = None,
    ) -> str:
        """Patrón orquestador/obrero. OBREROS (modelo chico) redactan cada
        componente; el ORQUESTADOR (modelo potente, self._ai) integra todo.

        Resiliente: si un componente falla o se cuelga, NO mata toda la generación
        (que puede ser de muchos componentes); deja un placeholder y sigue. Reporta
        el avance por `progress` para que no parezca colgado."""
        if self._ai is None:
            raise RuntimeError("No hay proveedor de IA configurado (revisá config.toml)")
        worker = self._section_provider(tipo)
        worker_unavailable = False  # si el obrero da 401, caemos al principal

        parts: list[str] = []
        total = len(extracted.components)
        for i, comp in enumerate(extracted.components, 1):
            if progress:
                progress(f"Documentando componente {i}/{total}: «{comp.name}»…")
            system, user = ai_prompts.build_worker_section(comp, tipo, categoria_hint)
            activo = self._ai if worker_unavailable else worker
            try:
                part = activo.complete(system, user)
            except AIAuthError:
                # 401 del OBRERO: caemos al modelo principal para este y los próximos
                # (el manual se genera completo igual). Si el que falló ES el principal,
                # no hay con qué seguir → propaga (aborta con mensaje claro).
                if activo is self._ai:
                    raise
                worker_unavailable = True
                if progress:
                    progress("⚠ El modelo obrero devolvió 401 (no autorizado); "
                             "sigo con el modelo principal.")
                part = self._ai.complete(system, user)
            except Exception as exc:  # noqa: BLE001 — un componente no debe matar todo
                part = (
                    f"## {comp.name}\n\n[COMPLETAR] No se pudo documentar "
                    f"automáticamente este componente (error: {exc}). Revisalo a mano."
                )
            parts.append(part)
            if progress:  # mostramos lo redactado en vivo (panel de actividad)
                progress(f"✓ «{comp.name}» listo:\n{part}")

        if progress:
            progress(f"Integrando el manual completo ({total} componentes)…")
        system, user = ai_prompts.build_orchestrate(
            solution_name=extracted.name, parts=parts, tipo=tipo,
            categoria_hint=categoria_hint, author=author, area=area,
            fecha=self._fecha_o_hoy(fecha), developer=developer,
            version=extracted.version, diff=diff,
        )
        try:
            return self._ai.complete(system, user)
        except AIAuthError:
            raise  # 401 en la integración: abortar claro, no devolver un cascarón
        except Exception as exc:  # noqa: BLE001 — no perder lo redactado por los obreros
            # Si la integración final falla (ej: timeout con el prompt grande), NO
            # tiramos todo: devolvemos las secciones ya redactadas, en modo degradado.
            aviso = (
                f"[COMPLETAR] No se pudo integrar automáticamente el manual "
                f"(error: {exc}). Abajo van las secciones por componente, sin integrar; "
                "revisalas y unificalas a mano o reintentá la integración."
            )
            return aviso + "\n\n" + "\n\n".join(parts)

    # --- Seguimiento de cambios entre versiones ---------------------------

    def find_snapshot(self, unique_name: str) -> StoredSnapshot | None:
        """Última foto guardada de ese paquete (o None si nunca se importó)."""
        return self._snapshots.get(unique_name) if self._snapshots else None

    def diff_for(self, extracted: ExtractedPackage) -> DiffResult:
        """Compara el paquete recién extraído contra su última importación."""
        stored = self.find_snapshot(extracted.unique_name)
        return diff_package(stored.snapshot if stored else None, extracted)

    def save_snapshot(
        self, extracted: ExtractedPackage, *,
        manual_func_id: int | None = None, manual_tec_id: int | None = None,
    ) -> None:
        """Guarda la foto del paquete importado para poder comparar la próxima vez."""
        if self._snapshots is None:
            return
        self._snapshots.save(StoredSnapshot(
            snapshot=PackageSnapshot.from_package(extracted),
            manual_func_id=manual_func_id, manual_tec_id=manual_tec_id,
        ))

    # --- Completar huecos [COMPLETAR] -------------------------------------

    def pending_slots(self, markdown: str) -> list[pending.PendingSlot]:
        """Huecos [COMPLETAR] del manual (texto puro, no toca nada)."""
        return pending.find_pending(markdown)

    def ai_questions_for_pending(self, markdown: str) -> list[str]:
        """Una pregunta por hueco [COMPLETAR], formulada por la IA. NO toca la base."""
        slots = pending.find_pending(markdown)
        if not slots:
            return []
        system, user = ai_prompts.build_questions(slots)
        raw = self._ask_ai(system, user)
        return pending.parse_questions(raw, len(slots))

    def fill_pending(self, markdown: str, answers: list[str]) -> str:
        """Rellena los huecos con las respuestas (reemplazo exacto, por código)."""
        return pending.fill_pending(markdown, answers)

    def ai_complement(
        self, *, current_markdown: str, instructions: str, tipo: ManualType,
        categoria_hint: str,
    ) -> str:
        """Modo 5 → complementa un manual existente con info nueva. NO toca la base."""
        system, user = ai_prompts.build_complement(
            current_markdown=current_markdown, instructions=instructions,
            tipo=tipo, categoria_hint=categoria_hint,
        )
        return self._ask_ai(system, user)

    def ai_document_package_section(
        self, *, extracted: ExtractedPackage, tipo: ManualType, categoria_hint: str,
        progress: Callable[[str], None] | None = None,
    ) -> str:
        """Genera la documentación de un paquete como BLOQUE DE SECCIONES listo para
        ADJUNTAR a un manual existente. NO reescribe el manual destino.

        Clave anti-timeout: cada componente se documenta con UNA llamada de obrero
        (chica), y NO hay una llamada final de integración que re-emita todo. Así
        ninguna llamada se acerca al corte de ~120s del modelo. Cada componente se
        documenta por SU `kind` (modelo de Power BI, reporte, flujo, etc.).

        Resiliente: si un componente falla, deja un [COMPLETAR] y sigue (no pierde
        el resto). `progress` reporta el avance componente a componente."""
        if self._ai is None:
            raise RuntimeError("No hay proveedor de IA configurado (revisá config.toml)")
        # Atómico (sin sub-componentes): la unidad es el paquete mismo.
        componentes = extracted.components or [extracted]
        worker = self._section_provider(tipo)
        worker_unavailable = False
        total = len(componentes)
        partes: list[str] = []
        for i, comp in enumerate(componentes, 1):
            if progress:
                progress(f"Documentando «{comp.name}» ({i}/{total})…")
            system, user = ai_prompts.build_worker_section(comp, tipo, categoria_hint)
            activo = self._ai if worker_unavailable else worker
            try:
                parte = activo.complete(system, user)
            except AIAuthError:
                if activo is self._ai:
                    raise
                worker_unavailable = True
                if progress:
                    progress("⚠ El modelo obrero devolvió 401; sigo con el principal.")
                parte = self._ai.complete(system, user)
            except Exception as exc:  # noqa: BLE001 — un componente no mata la integración
                parte = (
                    f"## {comp.name}\n\n[COMPLETAR] No se pudo documentar "
                    f"automáticamente (error: {exc}). Revisalo a mano."
                )
            partes.append(parte)
            if progress:
                progress(f"✓ «{comp.name}» listo:\n{parte}")
        return "\n\n".join(partes)

    def ai_complement_with_package(
        self, *, current_markdown: str, extracted: ExtractedPackage, tipo: ManualType,
        categoria_hint: str,
    ) -> str:
        """Integra la ESTRUCTURA de un paquete (zip / Power BI) DENTRO de un manual
        YA existente —complementar, pero con material extraído en vez de texto—.

        Reusa el motor de complementar: una sola pasada que integra lo nuevo sin
        perder lo que había. El `kind` rutea el knowledge pack correcto. NO toca
        la base ni la red en sí (lo hace el proveedor de IA)."""
        system, user = ai_prompts.build_complement(
            current_markdown=current_markdown,
            instructions=extracted.summary_markdown,
            tipo=tipo, categoria_hint=categoria_hint, kind=extracted.kind,
            material_label=(
                "ESTRUCTURA EXTRAÍDA del paquete a integrar (verdad verificable: "
                "integrala fielmente en las secciones que correspondan)"
            ),
        )
        return self._ask_ai(system, user)

    def ai_from_transcription(
        self, *, transcription: str, tipo: ManualType, categoria_hint: str, author: str = "",
        area: str = "", fecha: str = "", developer: str = "",
    ) -> str:
        """Modo 3 → transcripción hablada a manual. NO toca la base."""
        system, user = ai_prompts.build_from_transcription(
            transcription=transcription, tipo=tipo, categoria_hint=categoria_hint,
            author=author, fecha=self._fecha_o_hoy(fecha), area=area, developer=developer,
        )
        return self._ask_ai(system, user)

    def markdown_to_section(self, title: str, markdown_text: str, order: int = 0) -> Section:
        """Helper: empaqueta Markdown en una Section lista para guardar.

        Conserva el Markdown original en source_markdown para re-editar después.
        """
        return Section(
            title=title,
            content_html=self._md_to_html(markdown_text),
            order=order,
            source_markdown=markdown_text,
        )

    def _ask_ai(self, system: str, user: str) -> str:
        if self._ai is None:
            raise RuntimeError("No hay proveedor de IA configurado (revisá config.toml)")
        return self._ai.complete(system, user)
