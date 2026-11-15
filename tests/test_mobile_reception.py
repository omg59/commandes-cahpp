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
from cahpp_app.horizon.operations import Operations
from cahpp_app.horizon.services import Cart

RELAY = Path(os.environ.get("HORIZON_SERVER_SOURCE", Path(__file__).resolve().parents[2] / "horizon-server")) / "relay.py"


@unittest.skipUnless(RELAY.is_file(), "Cloner également horizon-server pour le test inter-dépôts")
class MobileReceiptTest(unittest.TestCase):
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
                synchronize(b, pc)
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
