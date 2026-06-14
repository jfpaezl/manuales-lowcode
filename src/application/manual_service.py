"""ManualService: el caso de uso. Orquesta dominio, persistencia, PDF e IA.

La UI (PyQt) habla SOLO con este servicio. Nunca toca el repo, el renderer
ni la IA directamente. Si mañana cambiás de UI, este servicio no se entera.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date

from ..domain.entities import (
    Category, ExtractedPackage, Manual, ManualType, ManualVersion, Section,
)
from ..domain.ports import (
    AIProvider, CategoryRepository, ManualRepository, PackageExtractor, PDFRenderer,
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
    ) -> None:
        self._repo = repo
        self._renderer = renderer
        self._ai = ai
        self._md_to_html = md_to_html
        self._categories = categories
        self._extractor = extractor
        # "Obrero": modelo chico para la generación orquestada. Si no hay, se usa
        # el orquestador (self._ai) para todo (degrada con elegancia).
        self._worker_ai = worker_ai

    # --- IA: configuración en caliente ------------------------------------

    @property
    def ai_ready(self) -> bool:
        return self._ai is not None

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
        context: str = "", area: str = "", fecha: str = "",
    ) -> str:
        """Modo 1 → devuelve Markdown. NO toca la base: seguro en otro hilo."""
        system, user = ai_prompts.build_generate(
            topic=topic, tipo=tipo, categoria_hint=categoria_hint,
            author=author, fecha=self._fecha_o_hoy(fecha), context=context, area=area,
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
        author: str = "", area: str = "", fecha: str = "",
    ) -> str:
        """Modo 4 → de la estructura extraída de un paquete a manual. NO toca la base.

        Si el paquete trae VARIOS componentes (ej: una Solution), usa el patrón
        orquestador/obrero: el modelo chico redacta cada componente, el potente
        integra. Si es atómico, una sola llamada."""
        if len(extracted.components) > 1:
            return self._orchestrate(extracted, tipo, categoria_hint, author, area, fecha)
        system, user = ai_prompts.build_from_package(
            package_name=extracted.name, package_summary=extracted.summary_markdown,
            tipo=tipo, categoria_hint=categoria_hint,
            author=author, fecha=self._fecha_o_hoy(fecha), area=area,
        )
        return self._ask_ai(system, user)

    def _orchestrate(
        self, extracted: ExtractedPackage, tipo: ManualType, categoria_hint: str,
        author: str, area: str, fecha: str,
    ) -> str:
        """Patrón orquestador/obrero. OBREROS (modelo chico) redactan cada
        componente; el ORQUESTADOR (modelo potente, self._ai) integra todo."""
        if self._ai is None:
            raise RuntimeError("No hay proveedor de IA configurado (revisá config.toml)")
        worker = self._worker_ai or self._ai  # sin obrero → degrada al orquestador

        parts: list[str] = []
        for comp in extracted.components:
            system, user = ai_prompts.build_worker_section(comp, tipo, categoria_hint)
            parts.append(worker.complete(system, user))

        system, user = ai_prompts.build_orchestrate(
            solution_name=extracted.name, parts=parts, tipo=tipo,
            categoria_hint=categoria_hint, author=author, area=area,
            fecha=self._fecha_o_hoy(fecha),
        )
        return self._ai.complete(system, user)

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

    def ai_from_transcription(
        self, *, transcription: str, tipo: ManualType, categoria_hint: str, author: str = "",
        area: str = "", fecha: str = "",
    ) -> str:
        """Modo 3 → transcripción hablada a manual. NO toca la base."""
        system, user = ai_prompts.build_from_transcription(
            transcription=transcription, tipo=tipo, categoria_hint=categoria_hint,
            author=author, fecha=self._fecha_o_hoy(fecha), area=area,
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
