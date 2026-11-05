from __future__ import annotations

import tempfile
import threading
import unittest
from decimal import Decimal
from pathlib import Path

from cahpp_app.catalog_search import LatestCatalogSearchWorker
from cahpp_app.collaboration import CollaborationManager
from cahpp_app.database import Database, ProductSearchResult, SearchCancelled
from cahpp_app.numbers import parse_decimal, format_decimal, field_display_value


class Version150Test(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = Database(self.root / "local.sqlite3")
        with self.db.session() as c:
            self.supplier = c.execute(
                "INSERT INTO suppliers(name) VALUES ('TEST')"
            ).lastrowid
        self.lines = [
            {
                "designation": "GANT.TEST",
                "cartons": 2,
                "units_per_carton": 100,
                "unit_price": 0.12,
                "vat": 20,
            }
        ]

    def test_reopen_preserves_identity_and_invalidates_generated_documents(self):
        for prepared in (False, True):
            with self.subTest(prepared=prepared):
                order_id = self.db.save_order(self.supplier, self.lines)
                self.db.update_order_pdf(order_id, "exports/old.pdf")
                if prepared:
                    self.db.update_order_status(order_id, "E-mail préparé")
                before, lines = self.db.get_order(order_id)
                with self.assertRaises(ValueError):
                    self.db.save_order(self.supplier, self.lines, order_id=order_id)
                self.db.reopen_unsent_order(order_id)
                reopened, reopened_lines = self.db.get_order(order_id)
                for key in (
                    "id",
                    "order_number",
                    "shared_uid",
                    "order_date",
                    "total_ht",
                ):
                    self.assertEqual(reopened[key], before[key])
                self.assertEqual(
                    [dict(x) for x in lines], [dict(x) for x in reopened_lines]
                )
                self.assertEqual(reopened["status"], "Brouillon")
                self.assertEqual(reopened["pdf_path"], "")
                self.assertEqual(reopened["email_prepared_at"], "")
                self.assertGreater(
                    reopened["shared_revision"], before["shared_revision"]
                )
                self.db.save_order(
                    self.supplier, [{**self.lines[0], "cartons": 3}], order_id=order_id
                )
                self.assertEqual(self.db.get_order(order_id)[1][0]["cartons"], 3)
                self.assertTrue(
                    any(
                        x["action"] == "Commande reprise avant envoi"
                        for x in self.db.list_order_audit(order_id)
                    )
                )

    def test_sent_order_is_immutable_even_with_inconsistent_display_status(self):
        order_id = self.db.save_order(self.supplier, self.lines)
        self.db.update_order_status(order_id, "Envoyée")
        with self.db.session() as c:
            c.execute(
                "UPDATE orders SET status = 'Brouillon' WHERE id = ?", (order_id,)
            )
        before, lines = self.db.get_order(order_id)
        with self.assertRaises(ValueError):
            self.db.reopen_unsent_order(order_id)
        with self.assertRaises(ValueError):
            self.db.save_order(self.supplier, self.lines, order_id=order_id)
        after, kept = self.db.get_order(order_id)
        self.assertEqual(dict(before), dict(after))
        self.assertEqual([dict(x) for x in lines], [dict(x) for x in kept])

    def test_reopening_propagates_to_second_workstation(self):
        other = Database(self.root / "other.sqlite3")
        a = CollaborationManager(self.db, "a", "A", self.root / "shared")
        b = CollaborationManager(other, "b", "B", self.root / "shared")
        a.initialize_workspace()
        b.initialize_workspace()
        order_id = self.db.save_order(
            self.supplier, self.lines, order_number=a.reserve_order_number()
        )
        self.db.update_order_pdf(order_id, "absent-old.pdf")
        a.publish_order(order_id)
        b.sync_orders()
        self.db.reopen_unsent_order(order_id)
        a.publish_order(order_id)
        b.sync_orders()
        order = other.list_orders()[0]
        self.assertEqual(order["status"], "Brouillon")
        self.assertEqual(other.get_order(order["id"])[0]["pdf_path"], "")

    def test_numeric_validation_is_finite_and_does_not_transform_text(self):
        self.assertEqual(parse_decimal("1\u202f234,50"), Decimal("1234.50"))
        self.assertEqual(format_decimal("1.005", 2), "1,01")
        self.assertEqual(
            field_display_value("email", "prenom.nom@example.test", {"price"}),
            "prenom.nom@example.test",
        )
        for value in ("NaN", "Infinity", "-Infinity", "", "abc", True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_decimal(value)
        for field, value in (
            ("unit_price", "NaN"),
            ("unit_price", -1),
            ("cartons", 0),
            ("units_per_carton", -10),
            ("vat", 101),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.db.save_order(self.supplier, [{**self.lines[0], field: value}])
        self.assertEqual(self.db.list_orders(), [])

    def test_invalidation_cancels_without_submitting_another_query(self):
        started = threading.Event()
        cancelled = threading.Event()
        delivered = []

        class SlowDatabase:
            def search_products_detailed(self, **kwargs):
                started.set()
                if kwargs["cancel_event"].wait(2):
                    cancelled.set()
                    raise SearchCancelled()
                return ProductSearchResult([], "listing", 1)

        worker = LatestCatalogSearchWorker(SlowDatabase(), delivered.append)
        try:
            worker.submit(
                query="avant",
                supplier_id=None,
                favorite_only=False,
                limit=100,
                allow_slow_fallback=False,
            )
            self.assertTrue(started.wait(2))
            worker.invalidate()
            self.assertTrue(cancelled.wait(2))
            self.assertEqual(delivered, [])
        finally:
            worker.close()
