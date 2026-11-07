"""Recherche sélective sur grand catalogue, avec statistiques anciennes d'une seule ligne."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cahpp_app.database import Database
from cahpp_app.diagnostics import build_diagnostic_report


class CatalogSearchPerformanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.fixture.cleanup)
        cls.source = Database(Path(cls.fixture.name) / "fixture.sqlite3")
        with cls.source.session() as connection:
            connection.executemany(
                "INSERT INTO suppliers(id, name) VALUES (?, ?)",
                [(1, "TEST A"), (2, "TEST B")],
            )
            connection.execute(
                """INSERT INTO products(code_cahpp, designation, supplier_id, created_at, updated_at)
                   VALUES ('INITIAL', 'ARTICLE INITIAL', 1, '', '')"""
            )
            connection.execute("ANALYZE products")
            # Un ancien petit catalogue devient grand ; sqlite_stat1 reste périmée.
            connection.executemany(
                """INSERT INTO products(code_cahpp, supplier_ref, designation, supplier_id,
                       supplier_name, favorite, active, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, '', '')""",
                (
                    (
                        f"DM{i:07d}",
                        f"REF{i:07d}",
                        f"COMPRESSE STERILE {i:07d}"
                        if i % 503 == 0
                        else f"ARTICLE COURANT {i:07d}",
                        i % 2 + 1,
                        "TEST",
                        int(i == 503),
                        int(i != 1006),
                    )
                    for i in range(1, 20001)
                ),
            )
        if not cls.source.rebuild_search():
            raise AssertionError("Index de test non construit")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "local.sqlite3"
        self.source.backup(path)
        self.db = Database(path)

    def test_stale_statistics_do_not_force_a_scan_for_each_article(self):
        with self.db.connect() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT stat FROM sqlite_stat1 WHERE idx = 'idx_products_favorite'"
                )
                .fetchone()[0]
                .split()[0],
                "1",
            )
        result = self.db.search_products_detailed("compresse", limit=101)
        self.assertEqual(result.mode, "fts5")
        self.assertEqual(len(result.rows), 38)
        self.assertFalse(result.repaired, "Un index sain ne doit pas être reconstruit")
        self.assertTrue(self.db.search_plan_preparation["success"])

        # Budget de travail SQLite, indépendant de la vitesse du runner.
        # L'ancienne requête sur statistiques périmées dépasse ce budget.
        with self.db.connect() as connection:
            steps = 0

            def budget():
                nonlocal steps
                steps += 1000
                return int(steps > 100000)

            connection.set_progress_handler(budget, 1000)
            for query, expected in (("compresse", 38), ("introuvable", 0)):
                rows = self.db._execute_fts_search(
                    connection,
                    self.db._fts_query(query),
                    "p.active = 1",
                    [],
                    101,
                )
                self.assertEqual(len(rows), expected)
            self.assertLess(steps, 100000)

    def test_filters_priority_overrides_and_pagination_are_preserved(self):
        with self.db.session() as connection:
            product_id = connection.execute(
                "SELECT id FROM products WHERE code_cahpp = 'DM0000503'"
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO product_overrides(product_id, designation, unit_price, updated_at) VALUES (?, ?, ?, '')",
                (product_id, "COMPRESSE MODIFIEE", 2.5),
            )
        self.assertTrue(self.db.rebuild_search())
        result = self.db.search_products_detailed("compresse", limit=5)
        self.assertEqual(len(result.rows), 5)
        self.assertEqual(result.rows[0]["id"], product_id)
        self.assertEqual(result.rows[0]["designation"], "COMPRESSE MODIFIEE")
        self.assertEqual(result.rows[0]["unit_price"], 2.5)
        favorites = self.db.search_products_detailed("compresse", favorite_only=True)
        self.assertEqual([p["id"] for p in favorites.rows], [product_id])
        supplier = self.db.search_products_detailed("compresse", supplier_id=1)
        self.assertTrue(supplier.rows)
        self.assertTrue(all(p["supplier_id"] == 1 for p in supplier.rows))
        all_rows = self.db.search_products_detailed("compresse", include_inactive=True)
        self.assertEqual(len(all_rows.rows), 39)
        self.assertEqual(
            [
                p["id"]
                for p in self.db.search_products_detailed("compresse", limit=10).rows
            ][:5],
            [p["id"] for p in result.rows],
        )

    def test_diagnostic_explains_the_plan_without_recording_search_text(self):
        self.db.search_products_detailed("TEXTE_A_NE_PAS_EXPORTER")
        before = dict(self.db.search_plan_preparation)
        self.db.search_products_detailed("compresse")
        self.assertEqual(before, self.db.search_plan_preparation)
        report = build_diagnostic_report(self.db, None, "test")
        self.assertIn("Statistiques du planificateur : OK", report)
        self.assertIn("product_search", report)
        self.assertNotIn("TEXTE_A_NE_PAS_EXPORTER", report)
        self.assertTrue(self.db.search_index_status(deep=True)["consistent"])

    def test_catalog_rebuild_invalidates_the_previous_statistics(self):
        self.db.search_products_detailed("compresse")
        with self.db.session() as connection:
            connection.execute(
                """INSERT INTO products(code_cahpp, designation, supplier_id, created_at, updated_at)
                   VALUES ('NOUVEAU', 'NOUVEAU PRODUIT', 1, '', '')"""
            )
        self.assertTrue(self.db.rebuild_search())
        self.assertEqual(len(self.db.search_products_detailed("nouveau").rows), 1)
        with self.db.connect() as connection:
            estimated = (
                connection.execute(
                    "SELECT stat FROM sqlite_stat1 WHERE idx = 'idx_products_favorite'"
                )
                .fetchone()[0]
                .split()[0]
            )
            actual = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        self.assertEqual(int(estimated), actual)

    def test_statistics_failure_does_not_mark_a_healthy_index_as_corrupt(self):
        original = self.db.connect

        def blocked():
            connection = original()
            connection.set_authorizer(
                lambda action, *args: (
                    sqlite3.SQLITE_DENY
                    if action == sqlite3.SQLITE_ANALYZE
                    else sqlite3.SQLITE_OK
                )
            )
            return connection

        with patch.object(self.db, "connect", side_effect=blocked):
            self.db._prepare_search_statistics()
        self.assertFalse(self.db.search_plan_preparation["success"])
        self.assertTrue(self.db.fts_available)
        self.assertEqual(self.db.last_search_repair, {})
