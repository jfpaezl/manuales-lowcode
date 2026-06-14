"""Dispatcher: elige el extractor que reconoce cada paquete.

Es un PackageExtractor más (patrón Composite): la app le habla igual que a
cualquier extractor, y por dentro enruta al concreto que corresponda mirando
el CONTENIDO del ZIP. Agregar un formato nuevo = sumar un extractor a la lista.
"""
from __future__ import annotations

import zipfile
from collections.abc import Sequence
from io import BytesIO

from ...domain.entities import ExtractedPackage
from ...domain.ports import PackageExtractor, UnsupportedPackageError


class CompositePackageExtractor(PackageExtractor):
    def __init__(self, extractors: Sequence[PackageExtractor]) -> None:
        self._extractors = list(extractors)

    def supports(self, names: list[str]) -> bool:
        return any(e.supports(names) for e in self._extractors)

    def extract(self, data: bytes, filename: str = "") -> ExtractedPackage:
        try:
            names = zipfile.ZipFile(BytesIO(data)).namelist()
        except zipfile.BadZipFile as exc:
            raise UnsupportedPackageError("El archivo no es un ZIP válido.") from exc

        for extractor in self._extractors:
            if extractor.supports(names):
                return extractor.extract(data, filename)

        raise UnsupportedPackageError(
            "No reconozco este paquete. Por ahora soporto flujos de Power Automate "
            "y canvas apps de Power Apps exportados."
        )
