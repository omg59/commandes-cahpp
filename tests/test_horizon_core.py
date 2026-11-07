from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
import threading
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from cahpp_app.database import Database
from cahpp_app.horizon.bootstrap import configure, copy_database, initialize_profile
from cahpp_app.horizon.services import Cart, HorizonService, seed_demo


class HorizonCoreTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.db = Database(self.root / "source" / "data" / "commandes_cahpp.sqlite3")
        self.db.set_current_user("test", "Test")
        seed_demo(self.db)
        self.service = HorizonService(self.db)

    def search(self, **kwargs):
        return self.service.search(
            cancel=threading.Event(), progress=lambda *args: None, **kwargs
        ).rows

    def product(self, ref):
        with self.db.connect() as c:
            row = c.execute(
                "SELECT id FROM products WHERE supplier_ref=?", (ref,)
            ).fetchone()
        return self.db.get_product(row[0])

    def test_working_profiles_cannot_overwrite_an_existing_installation(self):
        with self.assertRaises(ValueError):
            initialize_profile(self.root / "source")
        profile = self.root / "empty"
        self.assertEqual(initialize_profile(profile)["mode"], "demo")
        self.assertEqual(
            initialize_profile(profile)["application"], "commandes-cahpp-horizon"
        )

    def test_profile_configuration_separates_data_and_resources(self):
        with patch.dict(os.environ, {}, clear=False):
            profile, info = configure(["--profile", str(self.root / "profile")])
            self.assertEqual(Path(os.environ["CAHPP_PORTABLE_ROOT"]), profile)
            self.assertTrue(
                (
                    Path(os.environ["CAHPP_RESOURCE_ROOT"])
                    / "ressources/horizon/ladapt.png"
                ).is_file()
            )
            self.assertEqual(info["mode"], "demo")

    def test_database_copy_includes_wal_and_leaves_source_and_collaboration_unchanged(
        self,
    ):
        self.db.save_settings(
            {"collaboration_enabled": "1", "collaboration_root": "source-network"}
        )
        with self.db.connect() as live:
            live.execute(
                "INSERT INTO settings(key,value) VALUES ('test_wal','present')"
            )
            live.commit()
            before = hashlib.sha256(self.db.path.read_bytes()).digest()
            profile = copy_database(self.db.path, self.root / "copies")
            self.assertEqual(hashlib.sha256(self.db.path.read_bytes()).digest(), before)
        local = Database(profile / "data/commandes_cahpp.sqlite3")
        self.assertEqual(local.get_settings()["test_wal"], "present")
        self.assertEqual(local.get_settings()["collaboration_enabled"], "0")
        self.assertEqual(self.db.get_settings()["collaboration_enabled"], "1")
        self.assertEqual(self.db.get_settings()["collaboration_root"], "source-network")
        p = local.get_product(self.product("DEMO-001")["id"])
        local.set_favorite(p["id"], False)
        self.assertTrue(self.product("DEMO-001")["favorite"])
        another = copy_database(self.db.path, self.root / "copies")
        self.assertNotEqual(profile, another)

    def test_invalid_or_future_database_is_refused_and_incomplete_copy_removed(self):
        invalid = self.root / "invalid.sqlite3"
        invalid.write_text("not a database")
        with self.assertRaises(ValueError):
            copy_database(invalid, self.root / "copies")
        self.assertEqual(list((self.root / "copies").iterdir()), [])
        with sqlite3.connect(self.db.path) as c:
            c.execute("PRAGMA user_version=999")
        with self.assertRaises(ValueError):
            copy_database(self.db.path, self.root / "copies")
        self.assertEqual(list((self.root / "copies").iterdir()), [])

    def test_demo_seed_is_idempotent_and_has_two_explicit_reviews(self):
        before = self.db.dashboard_stats()
        seed_demo(self.db)
        self.assertEqual(self.db.dashboard_stats()["products"], before["products"])
        self.assertEqual(len(self.search()), 8)
        self.assertEqual(len(self.search(review=True)), 2)
        self.assertTrue(
            all(row["code_cahpp"].startswith("DEMO-") for row in self.search())
        )

    def test_cart_decimal_totals_match_persisted_order_and_save_reuses_number(self):
        cart = Cart()
        cart.add(self.product("DEMO-001"), quantity=2)
        cart.add(self.product("DEMO-002"), quantity=3)
        self.assertEqual(cart.total_ht, Decimal("14.7800"))
        self.assertEqual(cart.total_ttc, Decimal("17.7360"))
        oid = cart.save(self.db, "Note", "Service de test")
        order, _ = self.db.get_order(oid)
        self.assertEqual(Decimal(str(order["total_ht"])), cart.total_ht)
        self.assertEqual(order["requester_service"], "Service de test")
        number = order["order_number"]
        cart.set_quantity(0, "1,5")
        self.assertEqual(cart.save(self.db), oid)
        self.assertEqual(self.db.get_order(oid)[0]["order_number"], number)

    def test_cart_refuses_unreviewed_inactive_and_another_supplier(self):
        cart = Cart()
        with self.assertRaises(ValueError):
            cart.add(self.product("DEMO-006"))
        cart.add(self.product("DEMO-001"))
        with self.assertRaises(ValueError):
            cart.add(self.product("DEMO-003"))
        before = cart.total_ht
        for value in ("0", "-1", "NaN", "inf"):
            with self.assertRaises(ValueError):
                cart.set_quantity(0, value)
        self.assertEqual(cart.total_ht, before)
        with self.db.session() as c:
            c.execute(
                "UPDATE products SET active=0 WHERE id=?",
                (self.product("DEMO-001")["id"],),
            )
        with self.assertRaises(ValueError):
            cart.save(self.db)

    def test_missing_price_is_not_treated_as_free(self):
        p = self.product("DEMO-001")
        p["unit_price"] = None
        with self.assertRaises(ValueError):
            Cart().add(p)
        cart = Cart()
        cart.add(p, price="0,1250")
        self.assertEqual(cart.total_ht, Decimal("12.5000"))

    def test_sent_order_cannot_be_loaded_as_an_editable_draft(self):
        cart = Cart()
        cart.add(self.product("DEMO-001"))
        oid = cart.save(self.db)
        self.db.update_order_status(oid, "Envoyée")
        with self.assertRaises(ValueError):
            Cart().load(self.db, oid)
        cart.set_quantity(0, 2)
        with self.assertRaises(ValueError):
            cart.save(self.db)

    def test_statistics_reconcile_and_exclude_drafts_and_deleted_orders(self):
        args = {"cancel": threading.Event(), "progress": lambda *args: None}
        stats = self.service.statistics(6, None, **args)
        self.assertEqual(stats["totals"]["orders"], 18)
        self.assertAlmostEqual(sum(stats["values"]), stats["totals"]["total_ht"])
        self.assertAlmostEqual(
            sum(row["total_ht"] for row in stats["suppliers"]),
            stats["totals"]["total_ht"],
        )
        self.assertEqual(len(stats["labels"]), 6)
        sid = stats["suppliers"][0]["id"]
        subset = self.service.statistics(3, sid, **args)
        self.assertEqual(subset["totals"]["orders"], 3)
        self.assertEqual(subset["totals"]["suppliers"], 1)
        self.assertEqual(len(subset["suppliers"]), 1)
        self.assertEqual(self.service.overview(**args)["review"], 2)

    def test_search_filters_and_limit_are_applied_in_sql(self):
        self.assertEqual(len(self.search(limit=2)), 2)
        self.assertEqual(len(self.search(query="nitrile")), 1)
        p = self.product("DEMO-001")
        self.assertTrue(
            all(
                row["supplier_id"] == p["supplier_id"]
                for row in self.search(supplier_id=p["supplier_id"])
            )
        )
        with self.db.session() as c:
            c.execute("UPDATE products SET active=0 WHERE id=?", (p["id"],))
        self.assertEqual(self.search(query="nitrile"), [])
        self.assertEqual(len(self.search(query="nitrile", include_inactive=True)), 1)
