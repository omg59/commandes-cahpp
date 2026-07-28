from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from openpyxl import load_workbook

from .database import Database


ProgressCallback = Callable[[int, int, str], None]


EXPECTED_COLUMNS = (
    "Catalogue",
    "IDFournisseur",
    "NomFournisseur",
    "CodeCahpp",
    "RéférenceArticle",
    "DésignationArticle",
    "ACL",
    "ACL13",
    "CIP13",
    "UCD13",
    "Conditionnement",
    "Qml",
    "TVA",
    "Nom_Classif",
    "Code_Classif",
    "PrixUnitaireCahpp",
    "PrixGAM",
    "EVOLUTION",
    "MAJTYPE",
    "LIBMAJOURETAT",
    "ZONE_FABRICATION",
    "SUBSTANCE_DANGEREUSE",
    "CONDITIONNEMENT_UNITAIRE",
    "MAJMOIS",
    "MarcheGAM",
)


@dataclass(frozen=True)
class ImportResult:
    import_id: int
    filename: str
    row_count: int
    added_count: int
    updated_count: int
    missing_count: int
    already_imported: bool = False


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _number(value: object) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    normalized = str(value).strip().replace(" ", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _chunks(rows: Iterable[tuple], size: int = 3000) -> Iterable[list[tuple]]:
    batch: list[tuple] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


class CatalogImporter:
    def __init__(self, database: Database):
        self.database = database

    def import_file(
        self, path: Path | str, progress: ProgressCallback | None = None
    ) -> ImportResult:
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(path)
        progress = progress or (lambda current, total, message: None)
        progress(0, 100, "Vérification du fichier...")
        file_hash = _sha256(path)

        with self.database.connect() as connection:
            previous = connection.execute(
                "SELECT * FROM imports WHERE file_hash = ?", (file_hash,)
            ).fetchone()
        if previous:
            return ImportResult(
                import_id=previous["id"],
                filename=previous["filename"],
                row_count=previous["row_count"],
                added_count=previous["added_count"],
                updated_count=previous["updated_count"],
                missing_count=previous["missing_count"],
                already_imported=True,
            )

        progress(2, 100, "Ouverture du classeur...")
        workbook = load_workbook(path, read_only=True, data_only=True)
        worksheet = workbook["TARIF_BASECOMPLETE"] if "TARIF_BASECOMPLETE" in workbook.sheetnames else workbook.active
        iterator = worksheet.iter_rows(values_only=True)
        try:
            header_values = next(iterator)
        except StopIteration as exc:
            raise ValueError("Le fichier Excel est vide.") from exc
        header = {_text(value): index for index, value in enumerate(header_values)}
        missing_columns = [name for name in EXPECTED_COLUMNS if name not in header]
        if missing_columns:
            raise ValueError(
                "Colonnes CAHPP manquantes : " + ", ".join(missing_columns)
            )

        total_rows = max(int(worksheet.max_row or 1) - 1, 1)
        connection = self.database.connect()
        try:
            connection.execute("PRAGMA temp_store = MEMORY")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DROP TABLE IF EXISTS temp.staging_catalog")
            connection.execute(
                """
                CREATE TEMP TABLE staging_catalog (
                    catalogue TEXT NOT NULL,
                    supplier_cahpp_id INTEGER,
                    supplier_name TEXT NOT NULL,
                    code_cahpp TEXT PRIMARY KEY,
                    supplier_ref TEXT NOT NULL,
                    designation TEXT NOT NULL,
                    acl TEXT NOT NULL,
                    acl13 TEXT NOT NULL,
                    cip13 TEXT NOT NULL,
                    ucd13 TEXT NOT NULL,
                    conditionnement REAL,
                    qml REAL,
                    vat REAL,
                    classification_name TEXT NOT NULL,
                    classification_code TEXT NOT NULL,
                    unit_price REAL,
                    gam_price REAL,
                    evolution TEXT NOT NULL,
                    update_type TEXT NOT NULL,
                    update_state TEXT NOT NULL,
                    manufacturing_zone TEXT NOT NULL,
                    hazardous TEXT NOT NULL,
                    unit_packaging TEXT NOT NULL,
                    update_month TEXT NOT NULL,
                    gam_market TEXT NOT NULL
                ) WITHOUT ROWID
                """
            )

            def normalized_rows() -> Iterable[tuple]:
                for values in iterator:
                    code = _text(values[header["CodeCahpp"]])
                    if not code:
                        continue
                    yield (
                        _text(values[header["Catalogue"]]),
                        int(_number(values[header["IDFournisseur"]]) or 0),
                        _text(values[header["NomFournisseur"]]),
                        code,
                        _text(values[header["RéférenceArticle"]]),
                        _text(values[header["DésignationArticle"]]),
                        _text(values[header["ACL"]]),
                        _text(values[header["ACL13"]]),
                        _text(values[header["CIP13"]]),
                        _text(values[header["UCD13"]]),
                        _number(values[header["Conditionnement"]]),
                        _number(values[header["Qml"]]),
                        _number(values[header["TVA"]]),
                        _text(values[header["Nom_Classif"]]),
                        _text(values[header["Code_Classif"]]),
                        _number(values[header["PrixUnitaireCahpp"]]),
                        _number(values[header["PrixGAM"]]),
                        _text(values[header["EVOLUTION"]]),
                        _text(values[header["MAJTYPE"]]),
                        _text(values[header["LIBMAJOURETAT"]]),
                        _text(values[header["ZONE_FABRICATION"]]),
                        _text(values[header["SUBSTANCE_DANGEREUSE"]]),
                        _text(values[header["CONDITIONNEMENT_UNITAIRE"]]),
                        _text(values[header["MAJMOIS"]]),
                        _text(values[header["MarcheGAM"]]),
                    )

            inserted = 0
            insert_sql = """
                INSERT INTO staging_catalog VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(code_cahpp) DO UPDATE SET
                    catalogue = excluded.catalogue,
                    supplier_cahpp_id = excluded.supplier_cahpp_id,
                    supplier_name = excluded.supplier_name,
                    supplier_ref = excluded.supplier_ref,
                    designation = excluded.designation,
                    acl = excluded.acl,
                    acl13 = excluded.acl13,
                    cip13 = excluded.cip13,
                    ucd13 = excluded.ucd13,
                    conditionnement = excluded.conditionnement,
                    qml = excluded.qml,
                    vat = excluded.vat,
                    classification_name = excluded.classification_name,
                    classification_code = excluded.classification_code,
                    unit_price = excluded.unit_price,
                    gam_price = excluded.gam_price,
                    evolution = excluded.evolution,
                    update_type = excluded.update_type,
                    update_state = excluded.update_state,
                    manufacturing_zone = excluded.manufacturing_zone,
                    hazardous = excluded.hazardous,
                    unit_packaging = excluded.unit_packaging,
                    update_month = excluded.update_month,
                    gam_market = excluded.gam_market
            """
            for batch in _chunks(normalized_rows()):
                connection.executemany(insert_sql, batch)
                inserted += len(batch)
                percent = min(70, 5 + int(inserted / total_rows * 65))
                progress(
                    percent,
                    100,
                    f"Lecture du catalogue : {inserted:,} articles".replace(",", " "),
                )

            row_count = connection.execute(
                "SELECT COUNT(*) FROM staging_catalog"
            ).fetchone()[0]
            now = datetime.now().isoformat(timespec="seconds")
            cursor = connection.execute(
                """
                INSERT INTO imports(filename, file_hash, imported_at, row_count)
                VALUES (?, ?, ?, ?)
                """,
                (path.name, file_hash, now, row_count),
            )
            import_id = int(cursor.lastrowid)

            progress(72, 100, "Comparaison avec le catalogue précédent...")
            connection.execute(
                """
                INSERT INTO suppliers(name, cahpp_id, updated_at)
                SELECT supplier_name, MIN(supplier_cahpp_id), ?
                FROM staging_catalog
                WHERE supplier_cahpp_id <> 0
                GROUP BY supplier_name
                ON CONFLICT(name) DO UPDATE SET
                    cahpp_id = excluded.cahpp_id,
                    updated_at = excluded.updated_at
                """,
                (now,),
            )

            added_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM staging_catalog s
                LEFT JOIN products p ON p.code_cahpp = s.code_cahpp
                WHERE p.id IS NULL
                """
            ).fetchone()[0]
            changed_condition = """
                p.catalogue IS NOT s.catalogue
                OR p.supplier_ref IS NOT s.supplier_ref
                OR p.designation IS NOT s.designation
                OR p.conditionnement IS NOT s.conditionnement
                OR p.qml IS NOT s.qml
                OR p.vat IS NOT s.vat
                OR p.unit_price IS NOT s.unit_price
                OR p.gam_price IS NOT s.gam_price
                OR p.supplier_name IS NOT s.supplier_name
            """
            updated_count = connection.execute(
                f"""
                SELECT COUNT(*)
                FROM staging_catalog s
                JOIN products p ON p.code_cahpp = s.code_cahpp
                WHERE {changed_condition}
                """
            ).fetchone()[0]
            missing_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM products p
                WHERE p.source = 'CAHPP' AND p.active = 1
                  AND NOT EXISTS (
                      SELECT 1 FROM staging_catalog s
                      WHERE s.code_cahpp = p.code_cahpp
                  )
                """
            ).fetchone()[0]

            connection.execute(
                f"""
                INSERT INTO price_history(
                    product_id, import_id, recorded_at,
                    unit_price, conditionnement, qml
                )
                SELECT p.id, ?, ?, s.unit_price, s.conditionnement, s.qml
                FROM staging_catalog s
                JOIN products p ON p.code_cahpp = s.code_cahpp
                WHERE p.unit_price IS NOT s.unit_price
                   OR p.conditionnement IS NOT s.conditionnement
                   OR p.qml IS NOT s.qml
                """,
                (import_id, now),
            )

            progress(78, 100, "Mise à jour des articles...")
            connection.execute(
                """
                INSERT INTO products(
                    code_cahpp, catalogue, supplier_id, supplier_cahpp_id, supplier_name,
                    supplier_ref, designation, acl, acl13, cip13, ucd13,
                    conditionnement, qml, vat, unit_price, gam_price,
                    classification_name, classification_code, evolution,
                    update_type, update_state, manufacturing_zone, hazardous,
                    unit_packaging, update_month, gam_market, active, source,
                    last_seen_import_id, created_at, updated_at
                )
                SELECT
                    s.code_cahpp, s.catalogue, f.id, s.supplier_cahpp_id, s.supplier_name,
                    s.supplier_ref, s.designation, s.acl, s.acl13, s.cip13,
                    s.ucd13, s.conditionnement, s.qml, s.vat, s.unit_price,
                    s.gam_price, s.classification_name, s.classification_code,
                    s.evolution, s.update_type, s.update_state,
                    s.manufacturing_zone, s.hazardous, s.unit_packaging,
                    s.update_month, s.gam_market, 1, 'CAHPP', ?, ?, ?
                FROM staging_catalog s
                LEFT JOIN suppliers f ON f.name = s.supplier_name
                WHERE 1
                ON CONFLICT(code_cahpp) DO UPDATE SET
                    catalogue = excluded.catalogue,
                    supplier_id = excluded.supplier_id,
                    supplier_cahpp_id = excluded.supplier_cahpp_id,
                    supplier_name = excluded.supplier_name,
                    supplier_ref = excluded.supplier_ref,
                    designation = excluded.designation,
                    acl = excluded.acl,
                    acl13 = excluded.acl13,
                    cip13 = excluded.cip13,
                    ucd13 = excluded.ucd13,
                    conditionnement = excluded.conditionnement,
                    qml = excluded.qml,
                    vat = excluded.vat,
                    unit_price = excluded.unit_price,
                    gam_price = excluded.gam_price,
                    classification_name = excluded.classification_name,
                    classification_code = excluded.classification_code,
                    evolution = excluded.evolution,
                    update_type = excluded.update_type,
                    update_state = excluded.update_state,
                    manufacturing_zone = excluded.manufacturing_zone,
                    hazardous = excluded.hazardous,
                    unit_packaging = excluded.unit_packaging,
                    update_month = excluded.update_month,
                    gam_market = excluded.gam_market,
                    active = 1,
                    last_seen_import_id = excluded.last_seen_import_id,
                    updated_at = excluded.updated_at
                """,
                (import_id, now, now),
            )
            connection.execute(
                """
                UPDATE products
                SET active = 0, updated_at = ?
                WHERE source = 'CAHPP'
                  AND last_seen_import_id IS NOT ?
                """,
                (now, import_id),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO price_history(
                    product_id, import_id, recorded_at,
                    unit_price, conditionnement, qml
                )
                SELECT p.id, ?, ?, p.unit_price, p.conditionnement, p.qml
                FROM products p
                WHERE p.last_seen_import_id = ?
                  AND NOT EXISTS (
                      SELECT 1 FROM price_history ph
                      WHERE ph.product_id = p.id
                  )
                """,
                (import_id, now, import_id),
            )
            connection.execute(
                """
                UPDATE imports
                SET row_count = ?, added_count = ?, updated_count = ?,
                    missing_count = ?
                WHERE id = ?
                """,
                (
                    row_count,
                    added_count,
                    updated_count,
                    missing_count,
                    import_id,
                ),
            )

            progress(88, 100, "Création de l'index de recherche...")
            self.database.rebuild_search(connection)
            connection.execute("DROP TABLE temp.staging_catalog")
            connection.commit()
            progress(100, 100, "Catalogue mis à jour.")
            return ImportResult(
                import_id=import_id,
                filename=path.name,
                row_count=row_count,
                added_count=added_count,
                updated_count=updated_count,
                missing_count=missing_count,
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
            workbook.close()
