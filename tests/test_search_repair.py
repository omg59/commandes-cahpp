from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cahpp_app.database import Database
from cahpp_app.diagnostics import build_diagnostic_report


class SearchRepairTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.db = Database(Path(temporary.name) / "local.sqlite3")
        with self.db.session() as connection:
            self.supplier = connection.execute(
                "INSERT INTO suppliers(name) VALUES ('TEST')"
            ).lastrowid
        self.product = self.db.create_manual_product(
            self.supplier,
            "REF001",
            "GANT NITRILE",
            10,
            0.1,
            20,
        )
        self.order = self.db.save_order(
            self.supplier,
            [
                {
                    "product_id": self.product,
                    "designation": "GANT NITRILE",
                    "cartons": 1,
                    "units_per_carton": 10,
                    "unit_price": 0.1,
                    "vat": 20,
                }
            ],
        )
        self.db.ensure_search_index()

    def business_snapshot(self):
        with self.db.connect() as connection:
            return {
                table: [
                    tuple(row)
                    for row in connection.execute(
                        f"SELECT * FROM {table} ORDER BY rowid"
                    )
                ]
                for table in (
                    "products",
                    "suppliers",
                    "orders",
                    "order_lines",
                    "order_audit",
                    "settings",
                )
            }

    def test_detects_broken_tokens_even_when_rows_and_content_match(self):
        # Simule un contenu lisible dont les jetons FTS ne sont plus à jour.
        # Les comptes, les identifiants et même les textes correspondent.
        with self.db.session() as connection:
            connection.execute(
                "UPDATE products SET designation = 'COMPRESSE STERILE' WHERE id = ?",
                (self.product,),
            )
            connection.execute(
                "UPDATE product_search_content SET c2 = 'COMPRESSE STERILE' WHERE id = ?",
                (self.product,),
            )
        self.db._fts_verified = False
        status = self.db.search_index_status(deep=True)
        self.assertEqual(status["products"], status["indexed"])
        self.assertEqual(status["mismatched"], 0)
        self.assertFalse(status["consistent"])
        before = self.business_snapshot()
        result = self.db.search_products_detailed("compresse")
        self.assertEqual([row["id"] for row in result.rows], [self.product])
        self.assertTrue(result.repaired)
        self.assertEqual(self.business_snapshot(), before)
        self.assertTrue(self.db.last_search_repair["success"])

    def test_manual_repair_recreates_an_incorrect_table_definition(self):
        before = self.business_snapshot()
        with self.db.session() as connection:
            rows = connection.execute("SELECT rowid, * FROM product_search").fetchall()
            connection.execute("DROP TABLE product_search")
            connection.execute(
                "CREATE TABLE product_search(code_cahpp, supplier_ref, designation, supplier_name)"
            )
            connection.executemany(
                "INSERT INTO product_search(rowid, code_cahpp, supplier_ref, designation, supplier_name) VALUES (?, ?, ?, ?, ?)",
                rows,
            )
        self.assertTrue(self.db.rebuild_search(manual=True))
        self.assertTrue(self.db.search_index_status(deep=True)["functional"])
        self.assertEqual(len(self.db.search_products_detailed("gant").rows), 1)
        self.assertEqual(self.business_snapshot(), before)
        report = build_diagnostic_report(self.db, None, "test")
        self.assertIn("Déclenchement : Manuelle", report)
        self.assertIn("Articles reconstruits : 1 / 1", report)
        self.assertIn("Test de recherche avec classement : OK", report)

    def test_failed_repair_rolls_back_and_reports_the_reason(self):
        before = self.business_snapshot()
        with patch.object(
            self.db,
            "_create_search_table",
            side_effect=sqlite3.OperationalError("database is locked"),
        ):
            self.assertFalse(self.db.rebuild_search(manual=True))
        self.assertEqual(self.business_snapshot(), before)
        with self.db.connect() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT rowid FROM product_search WHERE product_search MATCH 'gant'"
                ).fetchone()[0],
                self.product,
            )
        report = build_diagnostic_report(self.db, None, "test")
        self.assertIn("Résultat : ÉCHEC", report)
        self.assertIn("base est occupée", report)
        self.assertFalse(self.db.last_search_repair["success"])
        self.assertEqual(len(self.db.search_products_detailed("gant").rows), 1)
        self.assertTrue(self.db.rebuild_search(manual=True))

    def test_failed_repair_preserves_the_callers_transaction(self):
        with self.db.session() as connection:
            connection.execute(
                "UPDATE suppliers SET notes = 'import en cours' WHERE id = ?",
                (self.supplier,),
            )
            with patch.object(
                self.db,
                "_create_search_table",
                side_effect=sqlite3.OperationalError("no such module: fts5"),
            ):
                self.assertFalse(self.db.rebuild_search(connection))
            self.assertTrue(connection.in_transaction)
        self.assertEqual(
            self.db.get_supplier(self.supplier)["notes"], "import en cours"
        )
        self.assertTrue(self.db.search_index_status(deep=True)["consistent"])

    def test_automatic_failure_has_a_cooldown_but_manual_repair_can_retry(self):
        with self.db.session() as connection:
            connection.execute("DROP TABLE product_search")
        self.db._fts_verified = False
        with patch.object(
            self.db,
            "_create_search_table",
            side_effect=sqlite3.OperationalError("no such module: fts5"),
        ) as create:
            self.assertFalse(self.db.ensure_search_index()["consistent"])
            self.assertFalse(self.db.ensure_search_index()["consistent"])
            self.assertEqual(create.call_count, 1)
        self.assertTrue(self.db.rebuild_search(manual=True))
        self.assertEqual(len(self.db.search_products_detailed("gant").rows), 1)

    def test_empty_catalog_can_be_rebuilt_and_searched(self):
        empty = Database(self.db.path.with_name("empty.sqlite3"))
        self.assertTrue(empty.rebuild_search(manual=True))
        self.assertTrue(empty.search_index_status(deep=True)["consistent"])
        self.assertEqual(empty.search_products_detailed("inexistant").rows, [])
