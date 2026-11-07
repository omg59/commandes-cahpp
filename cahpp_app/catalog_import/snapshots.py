"""Catalogue partagé autonome, lisible même après plusieurs mois hors ligne."""

from __future__ import annotations

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell

from .formats import CATALOG_FIELDS, LEGACY_COLUMNS, SNAPSHOT_FORMAT


def _append_values(sheet, values):
    """Conserver les textes littéralement, même s'ils commencent par '='."""
    cells = []
    for value in values:
        cell = WriteOnlyCell(sheet, value=value)
        if isinstance(value, str):
            cell.data_type = "s"
        cells.append(cell)
    sheet.append(cells)


def export_snapshot(database, destination, result):
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("CATALOGUE_PARTAGE")
    header = list(LEGACY_COLUMNS)
    # Les versions antérieures à 1.6 refusent ce format avant toute écriture.
    header[3] = "CODE_CAHPP"
    sheet.append(header + ["ARTICLEACTIF", "CAHPP_REVIEW_TOKEN", "CAHPP_REVIEW_REASON"])
    try:
        with database.connect() as connection:
            connection.execute("BEGIN")
            latest = connection.execute(
                "SELECT file_hash FROM imports ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if latest is None or latest[0] != result.file_hash:
                raise ValueError(
                    "Un autre import a remplacé le catalogue à publier. Relancez la publication depuis sa version courante."
                )
            count = 0
            for row in connection.execute(
                "SELECT "
                + ",".join(CATALOG_FIELDS)
                + ",active,catalog_review_token,catalog_review_reason FROM products WHERE source='CAHPP' ORDER BY id"
            ):
                _append_values(sheet, row)
                count += 1
            effective = connection.execute(
                "SELECT value FROM settings WHERE key='catalog_effective_period'"
            ).fetchone()
            meta = workbook.create_sheet("CAHPP_META")
            for key, value in {
                "format": SNAPSHOT_FORMAT,
                "effective_period": effective[0] if effective else "",
                "source_name": result.filename,
                "source_sha256": result.file_hash,
            }.items():
                _append_values(meta, (key, value))
            workbook.save(destination)
            return count
    finally:
        workbook.close()
