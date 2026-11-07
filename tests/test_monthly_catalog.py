from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook, load_workbook

from cahpp_app.catalog_importer import (
    CatalogImporter,
    CatalogImportError,
    ImportOptions,
)
from cahpp_app.collaboration import CollaborationManager, CollaborationError
from cahpp_app.database import Database
from tests.test_workflow import create_catalog


MONTHLY_HEADERS = (
    "CODE_CATALOGUE",
    "CODE_FOURNISSEUR",
    "NOM_FOURNISSEUR",
    "CODE_CAHPP",
    "REFERENCE",
    "DESIGNATION_FOURNISSEUR",
    "ACL",
    "ACL13",
    "CIP 13",
    "UCD 13",
    "CLASSIFICATION",
    "CODE_CLASSIF",
    "PRIXCAHPP",
    "TVA",
    "ARTICLEACTIF",
    "HORSMARCHE",
    "EVOLUTIONS",
    "MAJTYPE",
    "LIBMAJOURETAT",
    "ZONE FABRICATION",
    "SUBSTANCE DANGEREUSE",
    "CONDITIONNEMENT UNITAIRE",
    "MOIS_MISEAJOUR",
)


def monthly_row(
    code="DM001",
    *,
    price=2.5,
    active="Oui",
    kind="MPH",
    state="PRIX A LA HAUSSE",
    month="novembre 2026",
):
    return {
        "CODE_CATALOGUE": "DM",
        "CODE_FOURNISSEUR": "11020",
        "NOM_FOURNISSEUR": "HARTMANN",
        "CODE_CAHPP": code,
        "REFERENCE": "REF-" + code,
        "DESIGNATION_FOURNISSEUR": "ARTICLE " + code,
        "PRIXCAHPP": price,
        "TVA": "20",
        "ARTICLEACTIF": active,
        "MAJTYPE": kind,
        "LIBMAJOURETAT": state,
        "MOIS_MISEAJOUR": month,
    }


def create_monthly(path, rows, *, header=MONTHLY_HEADERS, preamble=False):
    wb = Workbook()
    ws = wb.active
    ws.title = "Evo TARIFS"
    if preamble:
        ws.append(["Évolutions tarifaires"])
        ws.append([])
    ws.append(list(header))
    for row in rows:
        ws.append([row.get(label) for label in header])
    wb.save(path)
    wb.close()


class MonthlyCatalogTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.db = Database(self.root / "local.sqlite3")
        self.importer = CatalogImporter(self.db)
        self.base = self.root / "base.xlsx"
        create_catalog(
            self.base,
            [
                {
                    "Catalogue": "DM",
                    "IDFournisseur": 11020,
                    "NomFournisseur": "HARTMANN",
                    "CodeCahpp": f"DM00{i}",
                    "RéférenceArticle": f"REF-DM00{i}",
                    "DésignationArticle": f"ARTICLE DM00{i}",
                    "PrixUnitaireCahpp": i,
                    "Conditionnement": i * 10,
                    "Qml": i * 10,
                    "TVA": 20,
                }
                for i in range(1, 5)
            ],
        )
        self.base_result = self.importer.import_file(self.base)
        self.options = ImportOptions(confirm_baseline=True)

    def product(self, code, database=None):
        database = database or self.db
        with database.connect() as connection:
            row = connection.execute(
                "SELECT id FROM products WHERE code_cahpp=?", (code,)
            ).fetchone()
        return database.get_product(row[0])

    def snapshot(self):
        with self.db.connect() as connection:
            return {
                table: [
                    tuple(r)
                    for r in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")
                ]
                for table in (
                    "products",
                    "suppliers",
                    "imports",
                    "price_history",
                    "settings",
                    "orders",
                    "order_lines",
                    "product_overrides",
                )
            }

    def test_delta_preserves_absent_articles_orders_and_manual_corrections(self):
        original = self.product("DM004")
        order = self.db.save_order(
            original["supplier_id"],
            [
                {
                    "product_id": original["id"],
                    "designation": "HISTORIQUE",
                    "cartons": 1,
                    "units_per_carton": 40,
                    "unit_price": 4,
                    "vat": 20,
                }
            ],
        )
        old_order, old_lines = self.db.get_order(order)
        self.db.set_product_override(
            original["id"], "CORRIGE", "CORRECTION LOCALE", 40, "", 4.4, 20
        )
        self.db.set_favorite(original["id"], True)
        original = self.product("DM004")
        path = self.root / "novembre.xlsx"
        create_monthly(
            path,
            [
                monthly_row(),
                monthly_row(
                    "DM002",
                    active="NON",
                    price=None,
                    kind="SAC",
                    state="ARRET DE COMMERCIALISATION",
                ),
                monthly_row("DM003", kind="MMC", state="CHANGEMENT DE CONDITIONNEMENT"),
                monthly_row("DM005", kind="ANR", state="NOUVELLE REFERENCE"),
            ],
        )
        preview = self.importer.inspect_file(path)
        self.assertEqual((preview.mode, preview.period), ("delta", "2026-11"))
        result = self.importer.import_file(path, options=self.options, preview=preview)
        self.assertEqual(
            (result.added_count, result.missing_count, result.deactivated_count),
            (1, 0, 1),
        )
        self.assertEqual(self.product("DM001")["unit_price"], 2.5)
        self.assertEqual(self.product("DM001")["conditionnement"], 10)
        self.assertFalse(self.product("DM001")["catalog_review_required"])
        self.assertEqual(self.product("DM002")["active"], 0)
        self.assertEqual(self.product("DM004"), original)
        self.assertEqual(dict(self.db.get_order(order)[0]), dict(old_order))
        self.assertEqual(
            [dict(x) for x in self.db.get_order(order)[1]], [dict(x) for x in old_lines]
        )
        self.assertTrue(self.product("DM003")["catalog_review_required"])
        self.assertTrue(self.product("DM005")["catalog_review_required"])
        self.assertEqual(result.review_count, 2)
        self.assertTrue(self.importer.import_file(path).already_imported)
        with self.db.connect() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM imports").fetchone()[0], 2
            )

    def test_review_is_required_and_validation_is_bound_to_the_current_change(self):
        path = self.root / "novembre.xlsx"
        create_monthly(
            path,
            [monthly_row("DM003", kind="MMC", state="CHANGEMENT DE CONDITIONNEMENT")],
        )
        self.importer.import_file(path, options=self.options)
        p = self.product("DM003")
        line = {
            "product_id": p["id"],
            "designation": p["designation"],
            "cartons": 1,
            "units_per_carton": 30,
            "unit_price": 3,
            "vat": 20,
        }
        with self.assertRaises(ValueError):
            self.db.save_order(p["supplier_id"], [line])
        values = dict(
            supplier_ref=p["supplier_ref"],
            designation=p["designation"],
            conditionnement=35,
            unit_packaging="",
            unit_price=3,
            vat=20,
        )
        with self.assertRaises(ValueError):
            self.db.set_product_override(p["id"], **values)
        self.db.set_product_override(
            p["id"],
            **values,
            catalog_review_confirmed=True,
            reviewed_catalog_token=p["catalog_review_token"],
        )
        self.assertFalse(self.product("DM003")["catalog_review_required"])
        with self.assertRaises(ValueError):
            self.db.save_order(p["supplier_id"], [line])
        self.db.save_order(p["supplier_id"], [{**line, "units_per_carton": 35}])
        december = self.root / "decembre.xlsx"
        create_monthly(
            december,
            [
                monthly_row(
                    "DM003",
                    kind="MMC",
                    state="CHANGEMENT DE CONDITIONNEMENT",
                    month="décembre 2026",
                )
            ],
        )
        self.importer.import_file(december)
        self.assertTrue(self.product("DM003")["catalog_review_required"])
        with self.assertRaises(ValueError):
            self.db.set_product_override(
                p["id"],
                **values,
                catalog_review_confirmed=True,
                reviewed_catalog_token=p["catalog_review_token"],
            )

    def test_base_and_chronology_are_enforced_without_partial_changes(self):
        path = self.root / "novembre.xlsx"
        create_monthly(path, [monthly_row()])
        empty = CatalogImporter(Database(self.root / "empty.sqlite3"))
        with self.assertRaises(CatalogImportError):
            empty.import_file(path, options=self.options)
        before = self.snapshot()
        with self.assertRaises(CatalogImportError):
            self.importer.import_file(path)
        self.assertEqual(self.snapshot(), before)
        self.importer.import_file(path, options=self.options)
        for month in ("octobre 2026", "janvier 2027"):
            create_monthly(self.root / "incorrect.xlsx", [monthly_row(month=month)])
            before = self.snapshot()
            with self.assertRaises(CatalogImportError):
                self.importer.import_file(self.root / "incorrect.xlsx")
            self.assertEqual(self.snapshot(), before)
        revision = self.root / "revision.xlsx"
        create_monthly(revision, [monthly_row(price=9)])
        with self.assertRaises(CatalogImportError):
            self.importer.import_file(revision)
        self.importer.import_file(revision, options=ImportOptions(allow_revision=True))
        self.assertEqual(self.product("DM001")["unit_price"], 9)

    def test_invalid_rows_duplicates_empty_and_changed_files_roll_back(self):
        cases = [
            [],
            [monthly_row(), monthly_row(price=8)],
            [monthly_row(price="NaN")],
            [monthly_row(price="oops")],
            [monthly_row(active="inconnu")],
            [monthly_row(active=None)],
            [
                monthly_row(month="novembre 2026"),
                monthly_row("DM002", month="décembre 2026"),
            ],
        ]
        for index, rows in enumerate(cases):
            with self.subTest(index=index):
                path = self.root / f"invalid{index}.xlsx"
                create_monthly(path, rows)
                before = self.snapshot()
                with self.assertRaises(CatalogImportError):
                    self.importer.import_file(path, options=self.options)
                self.assertEqual(self.snapshot(), before)
        path = self.root / "modifie.xlsx"
        create_monthly(path, [monthly_row()])
        preview = self.importer.inspect_file(path)
        create_monthly(path, [monthly_row(price=8)])
        before = self.snapshot()
        with self.assertRaises(CatalogImportError):
            self.importer.import_file(path, options=self.options, preview=preview)
        self.assertEqual(self.snapshot(), before)

    def test_fts_failure_rolls_back_the_whole_import(self):
        path = self.root / "novembre.xlsx"
        create_monthly(path, [monthly_row()])
        before = self.snapshot()
        with patch.object(self.db, "rebuild_search", return_value=False):
            with self.assertRaises(CatalogImportError):
                self.importer.import_file(path, options=self.options)
        self.assertEqual(self.snapshot(), before)

    def test_late_cancellation_rolls_back_before_commit(self):
        source = self.root / "novembre.xlsx"
        create_monthly(source, [monthly_row()])
        before = self.snapshot()

        def cancelled(current, total, message):
            if current == total:
                raise ValueError("Fermeture demandée")

        with self.assertRaises(ValueError):
            self.importer.import_file(source, options=self.options, progress=cancelled)
        self.assertEqual(self.snapshot(), before)

    def test_headers_and_future_optional_columns_are_tolerated(self):
        path = self.root / "novembre.xlsx"
        header = list(MONTHLY_HEADERS) + ["Conditionnement", "Qml", "CHAMP_FUTUR"]
        row = monthly_row("DM005", price="1\u202f234,50")
        row.update(Conditionnement=12, Qml=12, CHAMP_FUTUR="information supplémentaire")
        create_monthly(path, [row], header=header, preamble=True)
        self.importer.import_file(path, options=self.options)
        product = self.product("DM005")
        self.assertEqual(
            (product["unit_price"], product["conditionnement"]), (1234.5, 12)
        )
        self.assertFalse(product["catalog_review_required"])

    def test_simultaneous_reimport_is_idempotent(self):
        path = self.root / "novembre.xlsx"
        create_monthly(path, [monthly_row()])
        other = Database(self.db.path)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda db: CatalogImporter(db).import_file(
                        path, options=self.options
                    ),
                    [self.db, other],
                )
            )
        self.assertEqual(sum(result.already_imported for result in results), 1)
        self.assertEqual(self.product("DM001")["unit_price"], 2.5)

    def test_shared_snapshot_catches_up_an_offline_and_a_new_workstation(self):
        shared = self.root / "shared"
        a = CollaborationManager(self.db, "a", "A", shared)
        a.initialize_workspace()
        a.publish_catalog(self.base, self.base_result)
        november = self.root / "novembre.xlsx"
        create_monthly(
            november,
            [
                monthly_row(),
                monthly_row("DM002", active="NON", kind="SAC"),
                monthly_row("DM005", kind="ANR"),
            ],
        )
        result = self.importer.import_file(november, options=self.options)
        a.publish_catalog(november, result)
        december = self.root / "decembre.xlsx"
        create_monthly(december, [monthly_row("DM003", price=8, month="décembre 2026")])
        result = self.importer.import_file(december)
        current = a.publish_catalog(december, result)
        self.assertEqual(current["format"], 2)
        self.assertEqual(
            (a.catalogs_dir / current["source_relative_path"]).read_bytes(),
            december.read_bytes(),
        )
        for name, with_base in (("offline", True), ("nouveau", False)):
            db = Database(self.root / f"{name}.sqlite3")
            if with_base:
                CatalogImporter(db).import_file(self.base)
            manager = CollaborationManager(db, name, name, shared)
            manager.initialize_workspace()
            pending = manager.pending_catalog()
            source = manager.catalog_source(pending)
            CatalogImporter(db).import_file(source)
            manager.mark_catalog_applied(pending)
            self.assertIsNone(manager.pending_catalog())
            for code in ("DM001", "DM002", "DM003", "DM004", "DM005"):
                first, second = self.product(code), self.product(code, db)
                for field in (
                    "active",
                    "catalog_review_token",
                    "unit_price",
                    "conditionnement",
                    "qml",
                ):
                    self.assertEqual(first[field], second[field])
            wb = load_workbook(source, read_only=True)
            try:
                header = next(wb["CATALOGUE_PARTAGE"].iter_rows(values_only=True))
                self.assertNotIn(
                    "CodeCahpp", header
                )  # L'ancien importeur refuse avant écriture.
            finally:
                wb.close()

    def test_full_catalog_mass_removal_requires_explicit_confirmation(self):
        large = self.root / "complet.xlsx"
        rows = [
            {
                "Catalogue": "DM",
                "IDFournisseur": 11020,
                "NomFournisseur": "HARTMANN",
                "CodeCahpp": f"TEST{i}",
                "RéférenceArticle": f"T{i}",
                "DésignationArticle": "TEST",
                "Conditionnement": 10,
                "Qml": 10,
                "TVA": 20,
                "PrixUnitaireCahpp": 1,
            }
            for i in range(60)
        ]
        create_catalog(large, rows)
        self.importer.import_file(large)
        partial = self.root / "extrait.xlsx"
        create_catalog(partial, rows[:1])
        before = self.snapshot()
        with self.assertRaises(CatalogImportError):
            self.importer.import_file(partial)
        self.assertEqual(self.snapshot(), before)
        result = self.importer.import_file(
            partial, options=ImportOptions(confirm_full_replacement=True)
        )
        self.assertEqual((result.missing_count, result.deactivated_count), (59, 59))

    def test_new_full_format_respects_explicit_inactive_status(self):
        source = self.root / "complet-actifs.xlsx"
        wb = load_workbook(self.base)
        try:
            sheet = wb.active
            sheet.cell(1, sheet.max_column + 1, "ARTICLEACTIF")
            column = sheet.max_column
            for index in range(2, sheet.max_row + 1):
                sheet.cell(index, column, "NON" if index == 2 else "Oui")
            wb.save(source)
        finally:
            wb.close()
        self.assertEqual(self.importer.inspect_file(source).mode, "full")
        self.importer.import_file(source)
        self.assertEqual(self.product("DM001")["active"], 0)

    def test_legacy_full_catalog_accepts_its_empty_reserved_active_column(self):
        source = self.root / "octobre.xlsx"
        workbook = load_workbook(self.base)
        try:
            sheet = workbook.active
            sheet.cell(1, sheet.max_column + 1, "ARTICLEACTIF")
            sheet.cell(1, sheet.max_column + 1, "HORSMARCHE")
            workbook.save(source)
        finally:
            workbook.close()
        self.assertEqual(self.importer.inspect_file(source).mode, "full")
        self.importer.import_file(source)
        for i in range(1, 5):
            self.assertEqual(self.product(f"DM00{i}")["active"], 1)
        delta = self.root / "novembre.xlsx"
        create_monthly(delta, [monthly_row("DM001", active="NON", kind="SAC")])
        self.importer.import_file(delta, options=self.options)
        self.assertEqual(self.product("DM001")["active"], 0)
        self.assertEqual(self.product("DM002")["active"], 1)

    def test_unknown_action_is_reviewed_instead_of_assuming_unchanged_packaging(self):
        source = self.root / "futur.xlsx"
        create_monthly(
            source, [monthly_row(kind="NOUVEAU_CODE_CA HPP", state="ACTION FUTURE")]
        )
        self.importer.import_file(source, options=self.options)
        self.assertTrue(self.product("DM001")["catalog_review_required"])
        self.assertIn("non reconnu", self.product("DM001")["catalog_review_reason"])

    def test_review_confirmation_propagates_and_is_invalidated_by_a_later_delta(self):
        a = CollaborationManager(self.db, "a", "A", self.root / "shared")
        a.initialize_workspace()
        a.publish_catalog(self.base, self.base_result)
        source = self.root / "novembre.xlsx"
        create_monthly(
            source,
            [monthly_row("DM003", kind="MMC", state="CHANGEMENT DE CONDITIONNEMENT")],
        )
        result = self.importer.import_file(source, options=self.options)
        manifest = a.publish_catalog(source, result)
        other = Database(self.root / "other.sqlite3")
        CatalogImporter(other).import_file(a.catalog_source(manifest))
        product = self.product("DM003")
        self.db.set_product_override(
            product["id"],
            product["supplier_ref"],
            product["designation"],
            35,
            "",
            3,
            20,
            catalog_review_confirmed=True,
            reviewed_catalog_token=product["catalog_review_token"],
        )
        other.apply_team_state(self.db.export_team_state())
        self.assertFalse(self.product("DM003", other)["catalog_review_required"])
        self.assertEqual(self.product("DM003", other)["conditionnement"], 35)
        self.assertEqual(manifest["row_count"], 4)
        self.assertEqual(manifest["source_row_count"], 1)

    def test_failed_shared_publication_can_be_retried_without_reimporting(self):
        a = CollaborationManager(self.db, "a", "A", self.root / "shared")
        a.initialize_workspace()
        old = a.publish_catalog(self.base, self.base_result)
        source = self.root / "novembre.xlsx"
        create_monthly(source, [monthly_row()])
        result = self.importer.import_file(source, options=self.options)
        from cahpp_app.collaboration import _atomic_json, _read_json

        current = a.catalogs_dir / "catalogue-actuel.json"

        def failed(path, payload):
            if path == current:
                raise OSError("partage interrompu")
            return _atomic_json(path, payload)

        with patch("cahpp_app.collaboration._atomic_json", side_effect=failed):
            with self.assertRaises(OSError):
                a.publish_catalog(source, result)
        self.assertEqual(_read_json(current)["sha256"], old["sha256"])
        duplicate = self.importer.import_file(source)
        self.assertTrue(duplicate.already_imported)
        current = a.publish_catalog(source, duplicate)
        self.assertEqual(current["source_sha256"], duplicate.file_hash)
        with self.db.connect() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM imports").fetchone()[0], 2
            )

    def test_stale_publication_and_overwriting_unpublished_deltas_are_refused(self):
        shared = self.root / "shared"
        a = CollaborationManager(self.db, "a", "A", shared)
        a.initialize_workspace()
        base_manifest = a.publish_catalog(self.base, self.base_result)
        other = Database(self.root / "other.sqlite3")
        b = CollaborationManager(other, "b", "B", shared)
        b.initialize_workspace()
        CatalogImporter(other).import_file(b.catalog_source(base_manifest))
        b.mark_catalog_applied(base_manifest)
        source_a = self.root / "novembre-a.xlsx"
        source_b = self.root / "novembre-b.xlsx"
        create_monthly(source_a, [monthly_row(price=5)])
        create_monthly(source_b, [monthly_row(price=8)])
        result_a = self.importer.import_file(source_a, options=self.options)
        result_b = CatalogImporter(other).import_file(source_b, options=self.options)
        published = a.publish_catalog(source_a, result_a)
        with self.assertRaises(CollaborationError):
            b.publish_catalog(source_b, result_b)
        with self.assertRaises(CatalogImportError):
            CatalogImporter(other).import_file(b.catalog_source(published))
        CatalogImporter(other).import_file(
            b.catalog_source(published),
            options=ImportOptions(confirm_snapshot_replacement=True),
        )
        self.assertEqual(self.product("DM001", other)["unit_price"], 5)

    def test_supplier_rename_preserves_historical_identity_and_customer_details(self):
        product = self.product("DM001")
        supplier_id = product["supplier_id"]
        self.db.update_supplier(
            supplier_id,
            customer_number="CLIENT.TEST",
            email="test@example.invalid",
            phone="0102030405",
            franco_ht=100,
            notes="Informations locales",
        )
        order_id = self.db.save_order(
            supplier_id,
            [
                {
                    "product_id": product["id"],
                    "designation": "ARTICLE",
                    "cartons": 1,
                    "units_per_carton": 10,
                    "unit_price": 1,
                    "vat": 20,
                }
            ],
        )
        order, lines = self.db.get_order(order_id)
        old_order = dict(order), [dict(row) for row in lines]
        source = self.root / "renamed.xlsx"
        create_monthly(source, [{**monthly_row(), "NOM_FOURNISSEUR": "NOUVEAU NOM"}])
        self.importer.import_file(source, options=self.options)
        renamed = self.product("DM001")
        self.assertNotEqual(renamed["supplier_id"], supplier_id)
        with self.db.connect() as connection:
            old = connection.execute(
                "SELECT * FROM suppliers WHERE id=?", (supplier_id,)
            ).fetchone()
            new = connection.execute(
                "SELECT * FROM suppliers WHERE id=?", (renamed["supplier_id"],)
            ).fetchone()
        self.assertEqual(old["name"], "HARTMANN")
        self.assertEqual(new["name"], "NOUVEAU NOM")
        for key in ("customer_number", "email", "phone", "franco_ht", "notes"):
            self.assertEqual(new[key], old[key])
        order, lines = self.db.get_order(order_id)
        self.assertEqual((dict(order), [dict(row) for row in lines]), old_order)

    def test_unknown_vat_and_price_are_not_replaced_by_zero(self):
        source = self.root / "missing-values.xlsx"
        create_monthly(
            source,
            [
                {**monthly_row(kind="MMT", state="MODIFICATION TVA"), "TVA": None},
                {**monthly_row("DM005", price=None), "TVA": None},
            ],
        )
        self.importer.import_file(source, options=self.options)
        self.assertTrue(self.product("DM001")["catalog_review_required"])
        product = self.product("DM005")
        self.assertIsNone(product["unit_price"])
        self.assertIsNone(product["vat"])
        self.assertTrue(product["catalog_review_required"])

    def test_numeric_pack_changes_also_invalidate_existing_drafts(self):
        source = self.root / "numeric-pack.xlsx"
        header = list(MONTHLY_HEADERS) + ["Conditionnement", "Qml"]
        create_monthly(
            source, [{**monthly_row(), "Conditionnement": 15, "Qml": 15}], header=header
        )
        self.importer.import_file(source, options=self.options)
        product = self.product("DM001")
        self.assertTrue(product["catalog_review_required"])
        self.db.set_product_override(
            product["id"],
            product["supplier_ref"],
            product["designation"],
            15,
            "",
            2.5,
            20,
            catalog_review_confirmed=True,
            reviewed_catalog_token=product["catalog_review_token"],
        )
        with self.assertRaises(ValueError):
            self.db.validate_catalog_lines(
                [{"product_id": product["id"], "units_per_carton": 10}]
            )
        self.db.validate_catalog_lines(
            [{"product_id": product["id"], "units_per_carton": 15}]
        )

    def test_snapshot_preserves_text_that_looks_like_an_excel_formula(self):
        source = self.root / "novembre.xlsx"
        create_monthly(source, [monthly_row()])
        result = self.importer.import_file(source, options=self.options)
        with self.db.connect() as connection:
            connection.execute(
                "UPDATE products SET designation=? WHERE code_cahpp='DM001'",
                ("=ARTICLE + TEXTE",),
            )
            connection.commit()
        from cahpp_app.catalog_import.snapshots import export_snapshot

        snapshot = self.root / "snapshot.xlsx"
        export_snapshot(self.db, snapshot, result)
        other = Database(self.root / "other.sqlite3")
        CatalogImporter(other).import_file(snapshot)
        self.assertEqual(
            self.product("DM001", other)["designation"], "=ARTICLE + TEXTE"
        )

    def test_catalog_lock_keeps_its_longer_lifetime_when_refreshed(self):
        from datetime import datetime
        from cahpp_app.collaboration import _read_json

        a = CollaborationManager(self.db, "a", "A", self.root / "shared")
        a.initialize_workspace()
        with a.acquire_lock("systeme", "catalogue", ttl_seconds=600) as lock:
            lock.refresh()
            self.assertGreater(
                (
                    datetime.fromisoformat(_read_json(lock.path)["expires_at"])
                    - datetime.now()
                ).total_seconds(),
                590,
            )
