"""Contrats de migration, de calcul et d'échange des montants exacts."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from pypdf import PdfReader

from cahpp_app.database import SCHEMA, Database
from cahpp_app.horizon.services import Cart, currency
from cahpp_app.money_storage import SCHEMA_VERSION
from cahpp_app.pdf_export import generate_order_pdf


class ExactAmountsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "commandes.sqlite3"

    def seed_schema_16(self, unit_price=0.123456789):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executescript(SCHEMA.replace("DECIMAL_TEXT", "REAL"))
            db.execute("PRAGMA user_version=16")
            db.execute("INSERT INTO suppliers(id,name,franco_ht,minimum_order_ht) VALUES (1,'Test',0.105,0.01)")
            db.execute("""INSERT INTO products(id,code_cahpp,supplier_id,designation,unit_price,created_at,updated_at)
                        VALUES(20,'A',1,'Compresse',?,'','')""", (unit_price,))
            db.execute("INSERT INTO product_overrides(product_id,unit_price,updated_at) VALUES(20,0.1456789,'')")
            db.execute("""INSERT INTO orders(id,order_number,supplier_id,order_date,total_ht,total_vat,total_ttc,
                        shared_uid,shared_revision,sent_at,created_at,updated_at)
                        VALUES(22,'BC-TEST',1,'2026-11-18',1.005,0.201,1.206,?,4,'2026-11-18','','')""",
                       (str(uuid4()),))
            db.execute("""INSERT INTO order_lines(id,order_id,line_uid,product_id,designation,unit_price,total_ht)
                        VALUES(23,22,?,20,'Compresse',0.1005,1.005)""", (str(uuid4()),))
            db.execute("INSERT INTO order_attachments(order_id,display_name,stored_path,added_at) VALUES(22,'BL.pdf','BL.pdf','')")
            db.execute("UPDATE sqlite_sequence SET seq=100 WHERE name='products'")

    def test_schema_16_upgrade_keeps_amounts_ids_and_rollback_copy(self):
        self.seed_schema_16()
        db = Database(self.path)
        with closing(sqlite3.connect(self.path)) as raw:
            self.assertEqual(raw.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            self.assertEqual(raw.execute("SELECT typeof(unit_price),unit_price FROM products WHERE id=20").fetchone(),
                             ("text", "0.123456789"))
            self.assertEqual(raw.execute("PRAGMA foreign_key_check").fetchall(), [])
        order, lines = db.get_order(22)
        self.assertEqual((order["total_ht"], order["total_ttc"]), (Decimal("1.005"), Decimal("1.206")))
        self.assertEqual(lines[0]["unit_price"], Decimal("0.1005"))
        self.assertEqual(db.list_order_attachments(22)[0]["display_name"], "BL.pdf")
        self.assertEqual(db.get_product(20)["unit_price"], Decimal("0.1456789"))
        self.assertEqual(db.create_manual_product(1, "TEST", "Neuf", 1, "0.1", 20), 101)
        with closing(sqlite3.connect(db.amounts_backup)) as original:
            self.assertEqual(original.execute("PRAGMA user_version").fetchone()[0], 16)
            self.assertEqual(original.execute("SELECT total_ht FROM orders WHERE id=22").fetchone(), (1.005,))
        self.assertIsNone(Database(self.path).amounts_backup)

    def test_unconvertible_legacy_value_rolls_back_every_table(self):
        self.seed_schema_16("tarif indisponible")
        with self.assertRaisesRegex(ValueError, "Migration des montants interrompue"):
            Database(self.path)
        with closing(sqlite3.connect(self.path)) as raw:
            self.assertEqual(raw.execute("PRAGMA user_version").fetchone()[0], 16)
            self.assertEqual(raw.execute("SELECT typeof(franco_ht),franco_ht FROM suppliers").fetchone(), ("real", 0.105))
            self.assertEqual(raw.execute("SELECT unit_price FROM products").fetchone(), ("tarif indisponible",))
            self.assertEqual(raw.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_price_calculation_stats_and_shared_order_are_exact(self):
        db = Database(self.path)
        with db.session() as connection:
            sid = connection.execute("INSERT INTO suppliers(name) VALUES ('Test')").lastrowid
        price = Decimal("0.1234567890123456789")
        pid = db.create_manual_product(sid, "ART", "Article précis", 10, price, 20)
        cart = Cart()
        cart.add(db.get_product(pid), quantity=3)
        oid = cart.save(db)
        db.update_order_status(oid, "Envoyée")
        order, lines = db.get_order(oid)
        self.assertEqual(lines[0]["unit_price"], price)
        self.assertEqual((cart.total_ht, order["total_ht"], order["total_ttc"]),
                         (Decimal("3.7037"), Decimal("3.7037"), Decimal("4.4444")))
        day = date.fromisoformat(order["order_date"])
        self.assertEqual(db.statistics(day, day)["summary"]["total_ht"], Decimal("3.7037"))
        self.assertEqual(currency(Decimal("1.005")), "1,01 €")
        pdf = self.path.parent / "commande.pdf"
        generate_order_pdf(db, oid, pdf)
        extracted = "".join(page.extract_text() for page in PdfReader(pdf).pages)
        self.assertIn("3,70 €", extracted)
        self.assertIn("4,44 €", extracted)
        transferred = json.loads(json.dumps(db.export_order(oid)))
        another = Database(self.path.with_name("partage.sqlite3"))
        imported, _ = another.import_order(transferred)
        self.assertEqual(another.get_order(imported)[1][0]["unit_price"], price)
