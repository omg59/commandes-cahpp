"""Parcours HTTP réel, deux profils PC et perte d’accusé de réception.

Placer horizon-server à côté de horizon-pc pour exécuter le test inter-dépôts.
"""
import base64
import importlib.util
import io
import os
import tempfile
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from wsgiref.simple_server import make_server

from PIL import Image
from cahpp_app import local_services
from cahpp_app.database import Database
from cahpp_app.horizon.mobile_sync import Relay, synchronize
from cahpp_app.horizon.mobile_catalog import CatalogTransferPaused
from cahpp_app.horizon.operations import Operations
from cahpp_app.horizon.services import Cart

RELAY = Path(os.environ.get("HORIZON_SERVER_SOURCE", Path(__file__).resolve().parents[2] / "horizon-server")) / "relay.py"


@unittest.skipUnless(RELAY.is_file(), "Cloner également horizon-server pour le test inter-dépôts")
class MobileReceiptTest(unittest.TestCase):
    def test_compressed_publication_over_http_keeps_accented_search_working(self):
        spec = importlib.util.spec_from_file_location("horizon_test_relay_gzip", RELAY)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with ExitStack() as cleanup:
            root = Path(cleanup.enter_context(tempfile.TemporaryDirectory()))
            http = make_server("127.0.0.1", 0, module.create_app(root / "relay.db", "p" * 32, "m" * 32))
            worker = threading.Thread(target=http.serve_forever, daemon=True)
            worker.start()
            cleanup.callback(http.server_close)
            cleanup.callback(worker.join)
            cleanup.callback(http.shutdown)
            pc = Relay(f"http://127.0.0.1:{http.server_port}", "p" * 32)
            phone = Relay(f"http://127.0.0.1:{http.server_port}", "m" * 32)
            pc.catalog_gzip = pc.call("mobile-state")["catalog_gzip"]
            route = "catalog-sync/" + "a" * 64
            pc.call(route, {"parts": 1, "count": 100, "suppliers": []})
            pc.call(route + "/0", [{"code": f"ART-{i}", "label": "Compresses stériles",
                                   "supplier_id": "s1", "fingerprint": "a" * 64} for i in range(100)])
            pc.call(route + "/commit", {})
            result = phone.call("catalog?q=ster")
            self.assertEqual(len(result["items"]), 40)
            self.assertTrue(result["more"])

    def test_replay_after_lost_ack_two_workstations_and_two_pages(self):
        spec = importlib.util.spec_from_file_location("horizon_test_relay", RELAY)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with ExitStack() as cleanup:
            root = Path(cleanup.enter_context(tempfile.TemporaryDirectory()))
            desk_key, phone_key = "p" * 32, "m" * 32
            http = make_server("127.0.0.1", 0, module.create_app(root / "relay.db", desk_key, phone_key))
            worker = threading.Thread(target=http.serve_forever, daemon=True)
            worker.start()
            cleanup.callback(http.server_close)
            cleanup.callback(worker.join)
            cleanup.callback(http.shutdown)
            base = f"http://127.0.0.1:{http.server_port}"
            pc, phone = Relay(base, desk_key), Relay(base, phone_key)
            db = Database(root / "a/data/db.sqlite3")
            with db.session() as conn:
                sid = conn.execute("INSERT INTO suppliers(name) VALUES ('Fournisseur essai')").lastrowid
            pid = db.create_manual_product(sid, "ART-1", "Article essai", 10, 2, 20)
            db.backup(root / "b/data/db.sqlite3")
            other = Database(root / "b/data/db.sqlite3")
            for user, database in (("poste-a", db), ("poste-b", other)):
                database.save_settings({"user_id": user, "user_name": user, "collaboration_enabled": "1",
                                        "shared_workspace_path": str(root / "partage")})
            a, b = Operations(db), Operations(other)
            cleanup.callback(a.close)
            cleanup.callback(b.close)
            cleanup.enter_context(patch.object(local_services, "DOCUMENTS_DIR", root / "a/documents"))
            cart = Cart()
            cart.add(db.get_product(pid), quantity=1)
            oid = a.save_cart(cart)
            a.release_order()
            with a.locked_order(oid):
                db.update_order_status(oid, "Envoyée")
            synchronize(a, pc)
            order, = phone.call("orders")
            line, = order["lines"]
            self.assertEqual(line["remaining"], 10)
            photos = []
            for color in ("blue", "yellow"):
                jpeg = io.BytesIO()
                Image.new("RGB", (100, 200), color).save(jpeg, "JPEG")
                photos.append(base64.b64encode(jpeg.getvalue()).decode())
            route = "receipts/" + str(uuid4())
            receipt = {"order_id": order["id"], "date": "2026-11-15", "reference": "BL-test",
                       "quantities": {line["id"]: 6}, "pages": photos}
            self.assertEqual(phone.call(route, receipt)["state"], "pending")
            def lose_ack(endpoint, body=None):
                if endpoint.endswith("/result"):
                    raise ConnectionError("Coupure réseau")
                return Relay.call(pc, endpoint, body)
            with patch.object(pc, "call", lose_ack), self.assertRaises(ConnectionError):
                synchronize(a, pc)
            self.assertEqual(phone.call(route, receipt)["state"], "pending")
            with patch.object(local_services, "DOCUMENTS_DIR", root / "b/documents"):
                synchronize(b, pc)
                self.assertEqual(phone.call(route, receipt)["state"], "archived")
                other_id = other.list_orders()[0]["id"]
                for database, order_id in ((db, oid), (other, other_id)):
                    summary = database.receipt_summary(order_id)
                    self.assertEqual(len(summary["receipts"]), 1)
                    self.assertEqual(summary["lines"][0]["remaining_units"], 4)
                    attachment, = database.list_order_attachments(order_id)
                    pdf = local_services.resolve_portable_path(attachment["stored_path"]).read_bytes()
                    self.assertIn(b"/Count 2", pdf)
                self.assertEqual(phone.call("orders")[0]["lines"][0]["remaining"], 4)
                # Un autre téléphone avait chargé le reliquat avant la première réception.
                stale = "receipts/" + str(uuid4())
                phone.call(stale, receipt)
                synchronize(b, pc)
                self.assertEqual(phone.call(stale)["state"], "rejected")
                self.assertEqual(len(other.list_order_attachments(other_id)), 1)
                # Une réception sans photo ajoute des quantités sans créer un faux document.
                no_photo = dict(receipt, quantities={line["id"]: 2}, pages=[], without_document=True)
                no_photo_route = "receipts/" + str(uuid4())
                phone.call(no_photo_route, no_photo)
                with patch("cahpp_app.horizon.mobile_sync.publish_catalog",
                           side_effect=CatalogTransferPaused("Publication interrompue")):
                    status = synchronize(b, pc)
                self.assertIn("1 opération(s) archivée(s)", status)
                self.assertIn("Publication interrompue", status)
                self.assertEqual(phone.call(no_photo_route)["state"], "archived")
                self.assertEqual(other.receipt_summary(other_id)["lines"][0]["remaining_units"], 2)
                self.assertEqual(len(other.list_order_attachments(other_id)), 1)
                product = phone.call("catalog?q=Article")["items"][0]
                action_id = str(uuid4())
                action_route = "actions/" + action_id
                action = {"kind": "create", "lines": [{"code": product["code"],
                          "fingerprint": product["fingerprint"], "cartons": 2}], "notes": "Création mobile"}
                phone.call(action_route, action)
                original = pc.call
                def lose_action_ack(endpoint, body=None):
                    if endpoint == action_route + "/result":
                        raise ConnectionError("Accusé perdu")
                    return original(endpoint, body)
                with patch.object(pc, "call", lose_action_ack), self.assertRaises(ConnectionError):
                    synchronize(b, pc)
                synchronize(a, pc)
                self.assertEqual(phone.call(action_route)["state"], "archived")
                self.assertEqual(len(db.list_orders()), 2)
                self.assertEqual(len(other.list_orders()), 2)
                created = next(o for o in phone.call("order-history") if o["id"] == action_id)
                self.assertFalse(created["sent"])
                self.assertEqual(created["lines"][0]["units"], 20)
                document = next(d for d in created["documents"] if d["main"])
                self.assertTrue(base64.b64decode(phone.call("documents/" + document["id"])["data"]).startswith(b"%PDF"))
                def current_order():
                    return next(o for o in phone.call("order-history") if o["id"] == action_id)
                def command(kind, **fields):
                    snapshot = current_order()
                    payload = {"kind": kind, "order_id": action_id, "revision": snapshot["revision"], **fields}
                    path = "actions/" + str(uuid4())
                    phone.call(path, payload)
                    synchronize(a, pc)
                    self.assertEqual(phone.call(path)["state"], "archived")
                    return path, payload
                command("sent")
                self.assertTrue(current_order()["sent"])
                command("confirm")
                self.assertTrue(current_order()["confirmed"])
                stale_revision = current_order()["revision"]
                note_path, note_body = command("comment", text="Note envoyée depuis le téléphone")
                self.assertEqual(phone.call(note_path, note_body)["state"], "archived")
                stale_action = "actions/" + str(uuid4())
                phone.call(stale_action, {"kind": "invoiced", "order_id": action_id, "revision": stale_revision})
                synchronize(a, pc)
                self.assertEqual(phone.call(stale_action)["state"], "rejected")
                command("document", name="facture.pdf", document_kind="Facture", mime="application/pdf",
                        data=phone.call("documents/" + document["id"])["data"])
                self.assertEqual(len(current_order()["documents"]), 2)
                command("invoiced")
                self.assertTrue(current_order()["invoiced"])
                command("archive")
                self.assertTrue(current_order()["archived"])
                self.assertFalse(current_order()["receivable"])
                # Un tarif actualisé ne doit pas être remplacé par l'ancien prix du panier.
                with db.session() as c:
                    c.execute("UPDATE products SET unit_price=3 WHERE id=?", (pid,))
                outdated = "actions/" + str(uuid4())
                phone.call(outdated, action)
                synchronize(a, pc)
                self.assertEqual(phone.call(outdated)["state"], "rejected")
                self.assertEqual(len(db.list_orders(include_archived=True)), 2)
