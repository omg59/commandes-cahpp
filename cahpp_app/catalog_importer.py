"""API d'import historique ; implémentation séparée par responsabilité."""

from .catalog_import.engine import CatalogImporter
from .catalog_import.formats import (
    LEGACY_COLUMNS as EXPECTED_COLUMNS,
    CatalogImportError,
    ImportOptions,
    ImportPreview,
    ImportResult,
)

__all__ = [
    "CatalogImporter",
    "CatalogImportError",
    "ImportOptions",
    "ImportPreview",
    "ImportResult",
    "EXPECTED_COLUMNS",
]
