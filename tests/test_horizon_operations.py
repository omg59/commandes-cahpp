"""Régressions métier de la façade Qt, avec deux bases et un vrai partage."""

import hashlib
import json
import tempfile
import threading
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from cahpp_app.collaboration import ResourceLockedError
from cahpp_app.database import Database
from cahpp_app.diagnostics import build_diagnostic_report
from cahpp_app.horizon.bootstrap import copy_database
from cahpp_app.horizon.operations import Operations
from cahpp_app.horizon.services import Cart, HorizonService


class HorizonOperationsTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.db = Database(self.root / "one/data/commandes_cahpp.sqlite3")
        with self.db.session() as c:
            self.sid = c.execute(
                "INSERT INTO suppliers(name) VALUES ('Fournisseur essai')"
            ).lastrowid
        self.pid = self.db.create_manual_product(
            self.sid, "ART-1", "Article de test", 10, 1.25, 20
        )
        self.db.save_settings({"user_id": "poste-a", "user_name": "Poste A"})

    def cart(self, database=None):
        cart = Cart()
        cart.add((database or self.db).get_product(self.pid), quantity=2)
        return cart

    def pair(self):
        other_path = self.root / "two/data/commandes_cahpp.sqlite3"
        self.db.backup(other_path)
        other = Database(other_path)
        other.save_settings({"user_id": "poste-b", "user_name": "Poste B"})
        for db in (self.db, other):
            db.save_settings(
                {
                    "collaboration_enabled": "1",
                    "shared_workspace_path": str(self.root / "partage"),
                }
            )
        a, b = Operations(self.db), Operations(other)
        self.assertIsNotNone(a.manager, a.last_sync_error)
        self.assertIsNotNone(b.manager, b.last_sync_error)
        self.addCleanup(a.close)
        self.addCleanup(b.close)
        return a, b, other

    def sync(self, op):
        return op.sync(cancel=threading.Event(), progress=lambda *args: None)

    def test_two_posts_locks_numbering_partial_receipts_and_invoice_sync(self):
        a, b, other = self.pair()
        cart = self.cart()
        oid = a.save_cart(cart, "Note PDF", "Unité de test")
        number = self.db.get_order(oid)[0]["order_number"]
        self.sync(a)
        self.sync(b)
        remote = other.list_orders()[0]
        with self.assertRaises(ResourceLockedError):
            b.hold_order(remote["id"])
        a.release_order()
        with b.locked_order(remote["id"]):
            other.update_order_status(remote["id"], "Envoyée")
            other.mark_order_confirmed(
                remote["id"], True, expected_delivery_date=date.today()
            )
            uid = other.get_order(remote["id"])[1][0]["line_uid"]
            other.add_receipt(remote["id"], date.today(), {uid: 7}, "BL-1")
        self.sync(b)
        self.sync(a)
        self.assertEqual(
            self.db.get_order(oid)[0]["delivery_status"], "Partiellement livrée"
        )
        self.assertEqual(
            self.db.receipt_summary(oid)["lines"][0]["remaining_units"], 13
        )
        with a.locked_order(oid):
            self.db.add_receipt(oid, date.today(), {uid: 13}, "BL-2")
            self.db.mark_order_invoiced(oid)
        self.sync(a)
        self.sync(b)
        final = other.get_order(remote["id"])[0]
        self.assertEqual(final["delivery_status"], "Livrée")
        self.assertTrue(final["invoiced_at"])
        self.assertEqual(final["order_number"], number)
        next_cart = self.cart(other)
        next_oid = b.save_cart(next_cart)
        self.assertNotEqual(other.get_order(next_oid)[0]["order_number"], number)

    def test_lost_edit_lock_prevents_saving_and_preserves_existing_order(self):
        a, b, other = self.pair()
        cart = self.cart()
        oid = a.save_cart(cart)
        a.order_lock.release()
        cart.set_quantity(0, 8)
        with self.assertRaisesRegex(ValueError, "réservée"):
            a.save_cart(cart)
        self.assertEqual(self.db.get_order(oid)[1][0]["cartons"], 2)

    def test_nested_resources_do_not_release_the_outer_lock(self):
        a, b, other = self.pair()
        with a.locked_product(self.pid):
            with a.locked_product(self.pid):
                pass
            with self.assertRaises(ResourceLockedError):
                with b.locked_product(self.pid):
                    self.fail("Le verrou extérieur doit encore être détenu")
        with b.locked_product(self.pid):
            pass

    def test_background_work_rejects_ui_writes_without_blocking(self):
        op = Operations(self.db)
        acquired, finish = threading.Event(), threading.Event()

        def worker():
            with op.guard:
                acquired.set()
                finish.wait(3)

        thread = threading.Thread(target=worker)
        thread.start()
        try:
            self.assertTrue(acquired.wait(2))
            with self.assertRaisesRegex(ValueError, "synchronisation"):
                op.save_cart(self.cart())
        finally:
            finish.set()
            thread.join(3)

    def test_offline_profile_still_opens_for_reading_and_diagnostics(self):
        self.db.save_settings(
            {
                "collaboration_enabled": "1",
                "shared_workspace_path": str(self.root / "offline"),
            }
        )
        with patch(
            "cahpp_app.horizon.operations.CollaborationManager.initialize_workspace",
            side_effect=OSError("Réseau indisponible"),
        ):
            op = Operations(self.db)
        self.assertIn("Réseau indisponible", op.last_sync_error)
        self.assertTrue(self.db.get_product(self.pid))
        with self.assertRaisesRegex(ValueError, "indisponible"):
            op.save_cart(self.cart())
        report = build_diagnostic_report(
            self.db,
            op.manager,
            "2.0.0a2",
            last_sync_error=op.last_sync_error,
            gui_runtime="Interface : Qt",
        )
        self.assertIn("Réseau indisponible", report)
        self.db.save_settings({"collaboration_enabled": "0"})
        op.configure()
        self.assertTrue(op.save_cart(self.cart()))

    def test_diagnostic_works_without_tk_and_does_not_repair_silently(self):
        with self.db.session() as c:
            c.execute("DELETE FROM product_search")
        with patch.dict("sys.modules", {"tkinter": None}):
            before = build_diagnostic_report(
                self.db, None, "2.0.0a2", gui_runtime="Interface : Qt 6 / PySide6"
            )
        self.assertIn("À RÉPARER", before)
        self.assertIn("Qt 6", before)
        self.assertFalse(self.db.search_index_status(deep=True)["consistent"])
        self.db.rebuild_search(manual=True)
        after = build_diagnostic_report(
            self.db, None, "2.0.0a2", gui_runtime="Interface : Qt"
        )
        self.assertIn("Index de recherche : OK", after)
        self.assertIn("DERNIÈRE RECONSTRUCTION", after)
        self.assertNotIn("Article de test", after)

    def test_copy_rehomes_documents_and_logo_and_does_not_share_user_identity(self):
        root = self.db.path.parent.parent
        document = root / "documents/original.pdf"
        document.parent.mkdir()
        document.write_bytes(b"pdf historique de test")
        oid = self.cart().save(self.db)
        self.db.update_order_pdf(oid, str(document))
        self.db.add_order_attachment(
            oid, "Facture", document.name, "documents/original.pdf"
        )
        self.db.save_settings(
            {
                "logo_path": str(document),
                "shared_workspace_path": "partage-source",
                "pdf_default_directory": str(root / "exports"),
            }
        )
        before = hashlib.sha256(document.read_bytes()).hexdigest()
        profile = copy_database(self.db.path, self.root / "copies")
        copied = Database(profile / "data/commandes_cahpp.sqlite3")
        for value in [
            copied.get_order(oid)[0]["pdf_path"],
            copied.list_order_attachments(oid)[0]["stored_path"],
            copied.get_settings()["logo_path"],
        ]:
            file = profile / value
            self.assertTrue(file.is_file())
            self.assertIn(profile, file.parents)
            self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(), before)
        self.assertNotEqual(copied.get_settings()["user_id"], "poste-a")
        self.assertEqual(copied.get_settings()["shared_workspace_path"], "")
        self.assertEqual(copied.get_settings()["pdf_default_directory"], "")
        self.assertEqual(
            json.loads((profile / "horizon-profile.json").read_text())["copied_files"],
            3,
        )

    def test_only_horizon_installers_are_offered_and_prereleases_are_ordered(self):
        a, b, other = self.pair()
        updates = a.manager.updates_dir
        updates.mkdir(exist_ok=True)
        for name in [
            "CommandesCAHPP-Setup-99.0.0.exe",
            "CommandesCAHPP-Horizon-Setup-2.0.0a3.exe",
            "CommandesCAHPP-Horizon-Setup-2.0.0b1.exe",
            "CommandesCAHPP-Horizon-Setup-invalide.exe",
        ]:
            (updates / name).write_bytes(b"fixture")
        self.assertEqual(a.pending_installer("2.0.0a2")["version"], "2.0.0b1")
        self.assertIsNone(a.pending_installer("2.0.0a2", "2.0.0b1"))

    def test_statistics_custom_period_and_supplier_export_match_display(self):
        oid = self.cart().save(self.db)
        self.db.update_order_status(oid, "Envoyée")
        service = HorizonService(self.db)
        result = service.statistics(
            6,
            self.sid,
            date_from=date.today(),
            date_to=date.today(),
            cancel=threading.Event(),
            progress=lambda *args: None,
        )
        self.assertEqual(result["totals"]["orders"], 1)
        self.assertEqual(
            result["totals"]["total_ht"], result["detail"]["summary"]["total_ht"]
        )
        self.assertEqual(len(result["detail"]["products"]), 1)
        with self.assertRaises(ValueError):
            service.statistics(
                date_from=date(2030, 1, 2),
                date_to=date(2030, 1, 1),
                cancel=threading.Event(),
                progress=lambda *args: None,
            )

    def test_catalog_import_publishes_snapshot_and_second_post_applies_it(self):
        from cahpp_app.catalog_importer import CatalogImporter, ImportOptions
        from tests.test_workflow import create_catalog

        a, b, other = self.pair()
        source = self.root / "catalogue.xlsx"
        create_catalog(
            source,
            [
                {
                    "Catalogue": "DM",
                    "IDFournisseur": 999,
                    "NomFournisseur": "Partagé",
                    "CodeCahpp": "SHARED-001",
                    "RéférenceArticle": "SH-1",
                    "DésignationArticle": "Article CAHPP synchronisé",
                    "PrixUnitaireCahpp": 2.5,
                    "Conditionnement": 10,
                    "Qml": 10,
                    "TVA": 20,
                }
            ],
        )
        options = ImportOptions()
        args = {"cancel": threading.Event(), "progress": lambda *args: None}
        with patch("cahpp_app.paths.BACKUP_DIR", self.root / "backups"):
            a.import_catalog(
                source, CatalogImporter(self.db).inspect_file(source), options, **args
            )
            manifest = b.manager.pending_catalog()
            self.assertIsNotNone(manifest)
            snapshot = b.manager.catalog_source(manifest)
            preview = CatalogImporter(other).inspect_file(snapshot)
            b.import_catalog(
                snapshot,
                preview,
                ImportOptions(confirm_snapshot_replacement=True),
                shared_manifest=manifest,
                **args,
            )
        self.assertIsNone(b.manager.pending_catalog())
        products = other.search_products("SHARED-001")
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["unit_price"], 2.5)
        self.assertTrue(list((self.root / "backups").glob("*.zip")))
