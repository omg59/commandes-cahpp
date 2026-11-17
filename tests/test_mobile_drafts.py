"""Un relais, deux identités mobiles, deux postes et un brouillon partagé."""
import importlib.util
import os
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from wsgiref.simple_server import make_server

from cahpp_app import local_services
from cahpp_app.database import Database
from cahpp_app.horizon.mobile_sync import Relay, synchronize
from cahpp_app.horizon.operations import Operations
from cahpp_app.horizon.mobile_enrollment import enroll_device
from cahpp_app.horizon.services import Cart

RELAY = Path(os.environ.get("HORIZON_SERVER_SOURCE", Path(__file__).resolve().parents[2] / "horizon-server")) / "relay.py"


class ActorContextTest(unittest.TestCase):
    def test_mobile_identity_does_not_replace_pc_or_other_thread_identity(self):
        with tempfile.TemporaryDirectory() as folder, ThreadPoolExecutor(1) as pool:
            db = Database(Path(folder) / "db")
            db.set_current_user("pc", "Poste PC")
            with self.assertRaises(RuntimeError):
                with db.using_actor("mobile-alice", "Alice"):
                    self.assertEqual(db._actor(), ("mobile-alice", "Alice"))
                    self.assertEqual(pool.submit(db._actor).result(), ("pc", "Poste PC"))
                    raise RuntimeError("Opération interrompue")
            self.assertEqual(db._actor(), ("pc", "Poste PC"))


@unittest.skipUnless(RELAY.is_file(), "Cloner horizon-server pour le parcours inter-dépôts")
class MobileDraftTest(unittest.TestCase):
    def test_draft_round_trip_revision_conflict_lost_ack_and_two_users(self):
        spec = importlib.util.spec_from_file_location("draft_relay", RELAY)
        module = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", [str(RELAY.parent), *sys.path]):
            spec.loader.exec_module(module)
        with ExitStack() as stack:
            root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            http = make_server("127.0.0.1", 0, module.create_app(root / "relay.db", "p" * 32, "m" * 32))
            worker = threading.Thread(target=http.serve_forever, daemon=True)
            worker.start()
            stack.callback(http.server_close)
            stack.callback(worker.join)
            stack.callback(http.shutdown)
            url = f"http://127.0.0.1:{http.server_port}"
            pc, alice_phone, bob_phone = Relay(url, "p" * 32), Relay(url, "m" * 32), Relay(url, "m" * 32)
            alice, bob = {"id": str(uuid4()), "name": "Alice"}, {"id": str(uuid4()), "name": "Bob"}
            db = Database(root / "a/data/db")
            with db.session() as c:
                supplier = c.execute("INSERT INTO suppliers(name) VALUES('Fournisseur test')").lastrowid
            product_id = db.create_manual_product(supplier, "REF", "Article test", 10, 2, 20)
            db.backup(root / "b/data/db")
            other = Database(root / "b/data/db")
            for name, database in (("PC Alice", db), ("PC Bob", other)):
                database.save_settings({"user_id": str(uuid4()), "user_name": name, "collaboration_enabled": "1",
                                        "shared_workspace_path": str(root / "shared")})
            a, b = Operations(db), Operations(other)
            stack.callback(a.close)
            stack.callback(b.close)
            stack.enter_context(patch.object(local_services, "DOCUMENTS_DIR", root / "documents"))
            synchronize(a, pc)
            alice_phone.token = enroll_device(pc, "Alice", "Téléphone Alice")["token"]
            bob_phone.token = enroll_device(pc, "Bob", "Téléphone Bob")["token"]
            alice_phone.connect_workspace(a.manager.workspace_id)
            bob_phone.connect_workspace(a.manager.workspace_id)
            product = alice_phone.call("catalog?q=Article")["items"][0]
            draft_body = {"kind": "save_draft", "actor": alice, "lines": [{"code": product["code"],
                          "fingerprint": product["fingerprint"], "cartons": 2}], "notes": "À compléter", "service": "Soins"}
            uid = str(uuid4())
            route = "actions/" + uid
            alice_phone.call(route, draft_body)
            original_call = pc.call

            def lose_ack(endpoint, body=None):
                if endpoint == route + "/result":
                    raise ConnectionError("Accusé perdu")
                return original_call(endpoint, body)

            with patch.object(pc, "call", lose_ack), self.assertRaises(ConnectionError):
                synchronize(a, pc)
            synchronize(b, pc)
            self.assertEqual(alice_phone.call(route)["state"], "archived")
            self.assertEqual(len(db.list_orders()), 1)
            self.assertEqual(len(other.list_orders()), 1)
            current = bob_phone.call("order-history")[0]
            self.assertEqual(current["status"], "Brouillon")
            self.assertEqual(current["created_by"], "Alice")
            self.assertEqual(current["service"], "Soins")
            self.assertEqual(current["documents"], [])
            self.assertEqual(current["format"], 3)
            number = current["number"]
            other_id = other.list_orders()[0]["id"]
            # Modification PC pendant que le téléphone détient une version plus ancienne.
            with b.locked_order(other_id):
                cart = Cart()
                cart.load(other, other_id)
                cart.set_quantity(0, 3)
                other.save_order(cart.supplier_id, [line.as_mapping() for line in cart.lines],
                                 order_id=other_id, notes="Modifié sur PC", requester_service="Soins",
                                 selected_date=date(2026, 10, 1))
            stale = dict(draft_body, actor=bob, order_id=uid, revision=current["revision"])
            stale_route = "actions/" + str(uuid4())
            bob_phone.call(stale_route, stale)
            synchronize(b, pc)
            self.assertEqual(bob_phone.call(stale_route)["state"], "rejected")
            current = bob_phone.call("order-history")[0]
            self.assertEqual(current["lines"][0]["cartons"], 3)
            fresh = dict(stale, revision=current["revision"], notes="Complété par Bob")
            fresh["lines"] = [dict(fresh["lines"][0], cartons=4)]
            fresh_route = "actions/" + str(uuid4())
            bob_phone.call(fresh_route, fresh)
            synchronize(a, pc)
            self.assertEqual(bob_phone.call(fresh_route)["state"], "archived")
            current = alice_phone.call("order-history")[0]
            self.assertEqual(current["number"], number)
            self.assertEqual(current["date"], "2026-10-01")
            self.assertEqual(current["updated_by"], "Bob")
            self.assertEqual(current["status"], "Brouillon")
            self.assertEqual(current["documents"], [])
            # Finaliser le même brouillon génère le PDF, sans créer une deuxième commande.
            final = dict(fresh, kind="create", actor=alice, revision=current["revision"])
            final_route = "actions/" + str(uuid4())
            alice_phone.call(final_route, final)
            synchronize(b, pc)
            current = bob_phone.call("order-history")[0]
            self.assertEqual(current["number"], number)
            self.assertTrue(current["documents"])
            self.assertNotEqual(current["status"], "Brouillon")
            self.assertEqual(len(other.list_orders()), 1)
            # Les deux téléphones utilisent la même clé et conservent leurs auteurs dans l’audit.
            actors = {r["actor_name"] for r in other.list_order_audit(other_id)}
            self.assertTrue({"Alice", "Bob", "PC Bob"}.issubset(actors))
            self.assertEqual(db._actor()[1], "PC Alice")
            self.assertEqual(other._actor()[1], "PC Bob")
            # Un utilisateur peut ensuite réceptionner une commande préparée par un autre.
            sent = {"kind": "sent", "actor": alice, "order_id": uid, "revision": current["revision"]}
            alice_phone.call("actions/" + str(uuid4()), sent)
            synchronize(a, pc)
            current = bob_phone.call("order-history")[0]
            bob_phone.call("receipts/" + str(uuid4()), {"actor": bob, "order_id": uid, "date": "2026-11-16",
                           "quantities": {current["lines"][0]["id"]: 1}, "pages": [], "without_document": True})
            synchronize(b, pc)
            self.assertEqual(alice_phone.call("order-history")[0]["receipts"][0]["received_by"], "Bob")
