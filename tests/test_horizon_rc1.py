"""Cas de non-régression de la RC1 : pannes et histoires indépendantes."""

import json
import shutil
import sqlite3
import threading
import unittest
import zipfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

import test_horizon_operations as fixtures
from cahpp_app.collaboration import CollaborationError, SyncConflictError
from cahpp_app.database import Database
from cahpp_app.horizon.bootstrap import copy_database
from cahpp_app.horizon.services import HorizonService
from cahpp_app.local_services import create_complete_backup, prepare_mail_order
from cahpp_app.pdf_export import generate_order_pdf


class Rc1Test(unittest.TestCase):
    setUp = fixtures.HorizonOperationsTest.setUp
    cart = fixtures.HorizonOperationsTest.cart
    pair = fixtures.HorizonOperationsTest.pair
    sync = fixtures.HorizonOperationsTest.sync

    def shared_order(self):
        a, b, other = self.pair()
        oid = a.save_cart(self.cart())
        a.release_order()
        self.sync(b)
        return a, b, other, oid, other.list_orders()[0]["id"]

    def test_sequential_stale_posts_preserve_both_receipts_without_manual_sync(self):
        a, b, other, oid, bid = self.shared_order()
        with a.locked_order(oid):
            self.db.update_order_status(oid, "Envoyée")
            uid = self.db.get_order(oid)[1][0]["line_uid"]
            self.db.add_receipt(oid, date.today(), {uid: 7}, "BL-A")
        # B still has the pre-receipt snapshot; production facade refreshes under lock.
        with b.locked_order(bid):
            other.add_receipt(bid, date.today(), {uid: 6}, "BL-B")
        self.sync(a)
        self.assertEqual(self.db.receipt_summary(oid)["lines"][0]["received_units"], 13)
        self.assertEqual(other.receipt_summary(bid)["lines"][0]["remaining_units"], 7)

    def test_divergent_pending_changes_survive_sync_and_restart(self):
        a, b, other, oid, bid = self.shared_order()
        # Simulate an old/offline writer bypassing the facade.
        self.db.update_order_status(oid, "Envoyée")
        other.update_order_status(bid, "Envoyée")
        uid = self.db.get_order(oid)[1][0]["line_uid"]
        self.db.add_receipt(oid, date.today(), {uid: 7}, "A")
        other.add_receipt(bid, date.today(), {uid: 6}, "B")
        a.manager.publish_order(oid)
        Database(other.path)  # Migration/startup must not reset a dirty base.
        result = b.manager.sync_orders()
        self.assertGreater(result["conflicts"], 0)
        self.assertEqual(other.receipt_summary(bid)["lines"][0]["received_units"], 6)
        self.assertEqual(self.db.receipt_summary(oid)["lines"][0]["received_units"], 7)
        with self.assertRaises(SyncConflictError):
            b.manager.publish_order(bid)

    def test_same_number_different_identity_never_merges(self):
        oid = self.cart().save(self.db)
        payload = self.db.export_order(oid)
        import uuid

        payload["order"]["shared_uid"] = str(uuid.uuid4())
        payload["order"]["total_ht"] = 999
        with self.assertRaisesRegex(ValueError, "identité"):
            self.db.import_order(payload)
        self.assertNotEqual(self.db.get_order(oid)[0]["total_ht"], 999)

    def test_workspace_replacement_refused_without_overwriting_binding(self):
        a, b, other = self.pair()
        expected = self.db.get_settings()["collaboration_workspace_id"]
        manifest = a.manager.root / "espace-collaboratif.json"
        manifest.unlink()
        with self.assertRaises(CollaborationError):
            a.manager.initialize_workspace()
        self.assertFalse(manifest.exists())
        self.assertEqual(self.db.get_settings()["collaboration_workspace_id"], expected)
        manifest.write_text(json.dumps({"format": 1, "workspace_id": "autre-espace"}))
        with self.assertRaises(CollaborationError):
            a.manager.initialize_workspace()

    def test_invalid_shared_identifiers_are_rejected(self):
        a, b, other = self.pair()
        for value in ("", "identifiant-invalide", "commande/incorrecte"):
            with self.assertRaises(CollaborationError):
                a.manager._order_dir(value)

    def test_unchanged_sync_does_not_recopy_cached_files(self):
        a, b, other, oid, bid = self.shared_order()
        with patch.object(
            b.manager, "_cache_order_files", wraps=b.manager._cache_order_files
        ) as cache:
            result = b.manager.sync_orders()
        self.assertEqual(result["imported"], 0)
        cache.assert_not_called()

    def test_counter_recovers_local_history_then_does_not_scan_manifests(self):
        self.cart().save(self.db)
        a, b, other = self.pair()
        self.assertTrue(a.manager.reserve_order_number().endswith("0002"))
        with patch(
            "cahpp_app.collaboration._read_json",
            wraps=__import__(
                "cahpp_app.collaboration", fromlist=["_read_json"]
            )._read_json,
        ) as read:
            self.assertTrue(a.manager.reserve_order_number().endswith("0003"))
        self.assertFalse(
            any(str(c.args[0]).endswith("commande.json") for c in read.call_args_list)
        )

    def test_pdf_refuses_another_orders_file_and_preserves_content_on_render_failure(
        self,
    ):
        first = self.cart().save(self.db)
        second = self.cart().save(self.db)
        output = self.root / "2026-11-12 - BC-1.pdf"
        generate_order_pdf(self.db, first, output)
        original = output.read_bytes()
        with self.assertRaises(ValueError):
            generate_order_pdf(self.db, second, output)
        with patch(
            "cahpp_app.pdf_export._render_order_pdf",
            side_effect=OSError("disque indisponible"),
        ):
            with self.assertRaises(OSError):
                generate_order_pdf(self.db, first, output)
        self.assertEqual(output.read_bytes(), original)
        self.assertFalse(list(self.root.glob(".bon-*")))

    def test_backup_restores_external_pdf_logo_and_attachment_without_originals(self):
        oid = self.cart().save(self.db)
        external = self.root / "originaux"
        external.mkdir()
        pdf = external / "2026-11-12 - commande.pdf"
        generate_order_pdf(self.db, oid, pdf)
        logo = external / "logo.png"
        logo.write_bytes(b"logo")
        attachment = external / "bon de livraison.txt"
        attachment.write_bytes(b"BL")
        self.db.save_settings({"logo_path": str(logo)})
        self.db.add_order_attachment(
            oid, "Bon de livraison", attachment.name, str(attachment)
        )
        archive = self.root / "sauvegarde.zip"
        with patch("cahpp_app.local_services.DOCUMENTS_DIR", self.root / "documents"):
            create_complete_backup(self.db, archive)
        shutil.rmtree(external)
        extracted = self.root / "restauration"
        with zipfile.ZipFile(archive) as z:
            z.extractall(extracted)
        restored = copy_database(
            next((extracted / "data").glob("*.sqlite3")), self.root / "profiles"
        )
        c = sqlite3.connect(restored / "data/commandes_cahpp.sqlite3")
        try:
            self.assertEqual(c.execute("PRAGMA quick_check").fetchone()[0], "ok")
            paths = [
                c.execute("SELECT pdf_path FROM orders").fetchone()[0],
                c.execute(
                    "SELECT value FROM settings WHERE key='logo_path'"
                ).fetchone()[0],
                c.execute("SELECT stored_path FROM order_attachments").fetchone()[0],
            ]
            self.assertTrue(all((restored / p).is_file() for p in paths))
            self.assertEqual(Path(paths[2]).name, attachment.name)
        finally:
            c.close()

    def test_failed_backup_preserves_previous_archive(self):
        oid = self.cart().save(self.db)
        self.db.update_order_pdf(oid, str(self.root / "missing.pdf"))
        archive = self.root / "backup.zip"
        archive.write_bytes(b"ancienne sauvegarde")
        with self.assertRaisesRegex(ValueError, "incomplète"):
            create_complete_backup(self.db, archive)
        self.assertEqual(archive.read_bytes(), b"ancienne sauvegarde")

    def test_mail_missing_selected_attachment_stops_before_replacing_staging(self):
        oid = self.cart().save(self.db)
        with self.db.session() as c:
            c.execute(
                "UPDATE suppliers SET email=? WHERE id=?",
                ("test@example.invalid", self.sid),
            )
        generate_order_pdf(self.db, oid, self.root / "commande.pdf")
        self.db.add_order_attachment(
            oid,
            "Autre",
            "manquant.txt",
            str(self.root / "manquant.txt"),
            include_in_email=True,
        )
        with patch("cahpp_app.local_services.MAIL_PREP_DIR", self.root / "mail"):
            with self.assertRaisesRegex(ValueError, "Pièce jointe introuvable"):
                prepare_mail_order(self.db, oid)
            self.assertFalse((self.root / "mail").exists())

    def test_order_group_filter_precedes_limit_and_does_not_hide_old_pending_orders(
        self,
    ):
        old = self.cart().save(self.db)
        self.db.update_order_status(old, "Envoyée")
        for _ in range(502):
            self.cart().save(self.db)
        args = dict(cancel=threading.Event(), progress=lambda *a: None)
        rows = HorizonService(self.db).orders(group="À recevoir", **args)
        self.assertIn(old, [r["id"] for r in rows])

    def test_overview_skips_unused_product_statistics(self):
        service = HorizonService(self.db)
        with patch.object(
            service, "statistics_detail", side_effect=AssertionError("détails inutiles")
        ):
            service.overview(cancel=threading.Event(), progress=lambda *a: None)

    def test_publication_failure_retry_does_not_reimport_catalog(self):
        # Full import and publication failure use the real importer/workspace.
        from test_workflow import create_catalog
        from cahpp_app.catalog_importer import CatalogImporter
        from cahpp_app.catalog_import.formats import ImportOptions

        a, b, other = self.pair()
        source = self.root / "catalogue.xlsx"
        create_catalog(
            source,
            [
                {
                    "Catalogue": "DM",
                    "IDFournisseur": 999,
                    "NomFournisseur": "RC1",
                    "CodeCahpp": "RC1-1",
                    "RéférenceArticle": "RC1",
                    "DésignationArticle": "Article RC1",
                    "PrixUnitaireCahpp": 2.5,
                    "Conditionnement": 10,
                    "Qml": 10,
                    "TVA": 20,
                }
            ],
        )
        preview = CatalogImporter(self.db).inspect_file(source)
        args = dict(cancel=threading.Event(), progress=lambda *a: None)
        with (
            patch("cahpp_app.paths.BACKUP_DIR", self.root / "backups"),
            patch.object(
                a.manager, "publish_catalog", side_effect=OSError("réseau coupé")
            ),
        ):
            with self.assertRaises(OSError):
                a.import_catalog(source, preview, ImportOptions(), **args)
        self.assertTrue(self.db.get_settings().get("horizon_catalog_pending"))
        with self.db.connect() as c:
            before = c.execute("SELECT COUNT(*) FROM imports").fetchone()[0]
        source.unlink()  # Retried from durable copy, not original file.
        self.sync(a)
        self.assertFalse(self.db.get_settings().get("horizon_catalog_pending"))
        with self.db.connect() as c:
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM imports").fetchone()[0], before
            )

    def test_remote_commit_local_acknowledgement_failure_can_retry(self):
        a, b, other, oid, bid = self.shared_order()
        self.db.update_order_status(oid, "Envoyée")
        with patch.object(
            self.db, "mark_order_synced", side_effect=OSError("accusé local interrompu")
        ):
            with self.assertRaises(OSError):
                a.manager.publish_order(oid)
        a.manager.publish_order(oid)
        self.assertEqual(self.db.get_order(oid)[0]["sync_state"], "Synchronisée")
        self.sync(b)
        self.assertEqual(other.get_order(bid)[0]["status"], "Envoyée")

    def test_supplier_lock_key_is_stable_across_local_ids(self):
        a, b, other = self.pair()
        with self.db.session() as c:
            c.execute("UPDATE suppliers SET cahpp_id=42 WHERE id=?", (self.sid,))
        with other.session() as c:
            c.execute(
                "INSERT INTO suppliers(id,name,cahpp_id) VALUES (99,'Même fournisseur',42)"
            )
        from cahpp_app.collaboration import ResourceLockedError

        with a.resource("fournisseur", self.sid):
            with self.assertRaises(ResourceLockedError):
                with b.resource("fournisseur", 99):
                    pass

    def test_supplier_statistics_detail_is_filtered_before_ranking(self):
        first = self.cart().save(self.db)
        self.db.update_order_status(first, "Envoyée")
        with self.db.session() as c:
            sid = c.execute(
                "INSERT INTO suppliers(name) VALUES ('Petit fournisseur')"
            ).lastrowid
            # More expensive global references than the old 500-row limit.
            for n in range(501):
                c.execute(
                    "INSERT INTO order_lines(order_id,code_cahpp,supplier_ref,designation,cartons,units_per_carton,total_units,unit_price,vat,total_ht,line_uid) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        first,
                        str(n),
                        str(n),
                        "Référence " + str(n),
                        1,
                        1,
                        1,
                        100,
                        20,
                        100,
                        "ligne-" + str(n),
                    ),
                )
        pid = self.db.create_manual_product(sid, "petit", "Article à un euro", 1, 1, 20)
        from cahpp_app.horizon.services import Cart

        cart = Cart()
        cart.add(self.db.get_product(pid), quantity=1)
        second = cart.save(self.db)
        self.db.update_order_status(second, "Envoyée")
        stats = HorizonService(self.db).statistics(
            6, sid, cancel=threading.Event(), progress=lambda *a: None
        )
        self.assertEqual(len(stats["detail"]["products"]), 1)
        self.assertEqual(
            stats["detail"]["summary"]["total_ht"], stats["totals"]["total_ht"]
        )
