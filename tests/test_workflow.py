from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from openpyxl import Workbook
from pypdf import PdfReader

from cahpp_app.catalog_importer import CatalogImporter, EXPECTED_COLUMNS
from cahpp_app.database import Database
from cahpp_app import local_services
from cahpp_app.local_services import (
    attach_document,
    create_complete_backup,
    mark_order_sent,
    prepare_mail_order,
    remove_document,
)
from cahpp_app.pdf_export import generate_order_pdf
from cahpp_app.ui import (
    configured_pdf_directory,
    filter_supplier_names,
    fractional_carton_lines,
    suggested_pdf_filename,
)


def create_catalog(path: Path, rows: list[dict[str, object]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "TARIF_BASECOMPLETE"
    sheet.append(list(EXPECTED_COLUMNS))
    for row in rows:
        sheet.append([row.get(column) for column in EXPECTED_COLUMNS])
    workbook.save(path)


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.original_service_paths = (
            local_services.ROOT_DIR,
            local_services.DOCUMENTS_DIR,
            local_services.MAIL_PREP_DIR,
        )
        local_services.ROOT_DIR = self.root
        local_services.DOCUMENTS_DIR = self.root / "documents"
        local_services.MAIL_PREP_DIR = self.root / "envois"
        self.database = Database(self.root / "test.sqlite3")

    def tearDown(self):
        (
            local_services.ROOT_DIR,
            local_services.DOCUMENTS_DIR,
            local_services.MAIL_PREP_DIR,
        ) = self.original_service_paths
        self.temp.cleanup()

    def row(self, code, reference, designation, price, pack=100):
        return {
            "Catalogue": "DM",
            "IDFournisseur": 11020,
            "NomFournisseur": "HARTMANN",
            "CodeCahpp": code,
            "RéférenceArticle": reference,
            "DésignationArticle": designation,
            "Conditionnement": pack,
            "Qml": pack,
            "TVA": 20,
            "Nom_Classif": "CLADIMED",
            "Code_Classif": "TEST",
            "PrixUnitaireCahpp": price,
        }

    def test_import_search_order_and_pdf(self):
        self.assertEqual(
            filter_supplier_names(
                ["ABENA-FRANTEX", "HARTMANN", "MEDLINE"], "hart"
            ),
            ["HARTMANN"],
        )
        pdf_directory = self.root / "pdf-personnalises"
        pdf_directory.mkdir()
        self.database.save_settings(
            {"pdf_default_directory": str(pdf_directory)}
        )
        self.assertEqual(
            configured_pdf_directory(self.database), pdf_directory
        )

        first_path = self.root / "catalogue-1.xlsx"
        create_catalog(
            first_path,
            [
                self.row("DM001", "REF-A", "COMPRESSE TEST", 0.12, 100),
                self.row("DM002", "REF-B", "GANT TEST", 0.03, 1000),
            ],
        )
        first = CatalogImporter(self.database).import_file(first_path)
        self.assertEqual(first.row_count, 2)
        self.assertEqual(first.added_count, 2)

        products = self.database.search_products("compresse")
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["supplier_ref"], "REF-A")
        supplier_id = products[0]["supplier_id"]
        self.database.update_supplier(
            supplier_id,
            customer_number="CLIENT-42",
            email="commandes@example.test",
            phone="",
            franco_ht=50,
            notes="",
            contact_name="Service commandes",
            address="1 rue du Fournisseur",
            website="https://example.test",
            minimum_order_ht=25,
        )
        supplier = self.database.get_supplier(supplier_id)
        self.assertEqual(supplier["contact_name"], "Service commandes")
        self.assertEqual(float(supplier["minimum_order_ht"]), 25)
        self.database.save_settings(
            {
                "establishment_name": "Établissement de démonstration",
                "establishment_subtitle": "Service de soins",
                "address_line1": "1 rue du Test",
                "postal_city": "59000 Lille",
                "finess": "590000000",
            }
        )
        order_id = self.database.save_order(
            supplier_id,
            [
                {
                    "product_id": products[0]["id"],
                    "code_cahpp": products[0]["code_cahpp"],
                    "supplier_ref": products[0]["supplier_ref"],
                    "designation": products[0]["designation"],
                    "cartons": 2,
                    "units_per_carton": products[0]["conditionnement"],
                    "unit_price": products[0]["unit_price"],
                    "vat": products[0]["vat"],
                }
            ],
        )
        first_order, _ = self.database.get_order(order_id)
        self.assertEqual(
            suggested_pdf_filename(self.database, first_order),
            f"BC-{first_order['order_date']}_Hartmann.pdf",
        )
        self.assertEqual(
            fractional_carton_lines(
                [{"designation": "Test", "cartons": 1.5}]
            ),
            ["Test"],
        )
        second_order_id = self.database.save_order(
            supplier_id,
            [
                {
                    "product_id": products[0]["id"],
                    "code_cahpp": products[0]["code_cahpp"],
                    "supplier_ref": products[0]["supplier_ref"],
                    "designation": products[0]["designation"],
                    "cartons": 1,
                    "units_per_carton": products[0]["conditionnement"],
                    "unit_price": products[0]["unit_price"],
                    "vat": products[0]["vat"],
                }
            ],
        )
        second_order, _ = self.database.get_order(second_order_id)
        self.assertEqual(
            suggested_pdf_filename(self.database, second_order),
            f"BC-{second_order['order_date']}_2_Hartmann.pdf",
        )
        self.assertEqual(
            suggested_pdf_filename(self.database, first_order),
            f"BC-{first_order['order_date']}_Hartmann.pdf",
        )
        pdf_path = generate_order_pdf(
            self.database, order_id, self.root / "bon-test.pdf"
        )
        self.assertTrue(pdf_path.is_file())
        reader = PdfReader(pdf_path)
        self.assertEqual(len(reader.pages), 1)
        pdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        self.assertNotIn("Code CAHPP", pdf_text)
        self.assertNotIn("DM001", pdf_text)
        self.assertNotIn(
            "Bon de commande généré localement avec Commandes CAHPP",
            pdf_text,
        )

        duplicated_id = self.database.duplicate_order(order_id)
        duplicated_order, duplicated_lines = self.database.get_order(
            duplicated_id
        )
        self.assertEqual(duplicated_order["status"], "Brouillon")
        self.assertEqual(duplicated_order["supplier_id"], supplier_id)
        self.assertEqual(duplicated_lines[0]["unit_price"], 0.12)
        self.assertEqual(
            [row["id"] for row in self.database.list_orders(query="REF-A")],
            [duplicated_id, second_order_id, order_id],
        )

        delivery_note = self.root / "BL-42.pdf"
        delivery_note.write_bytes(b"%PDF-1.4\n% test\n")
        attachment_id = attach_document(
            self.database,
            order_id,
            delivery_note,
            "Bon de livraison",
            include_in_email=True,
        )
        attachments = self.database.list_order_attachments(order_id)
        self.assertEqual(len(attachments), 1)
        self.assertTrue(
            local_services.resolve_portable_path(
                attachments[0]["stored_path"]
            ).is_file()
        )
        compose_url, mail_folder, prepared = prepare_mail_order(
            self.database, order_id
        )
        compose_query = parse_qs(urlparse(compose_url).query)
        self.assertEqual(compose_query["to"], ["commandes@example.test"])
        self.assertIn(first_order["order_number"], compose_query["su"][0])
        self.assertEqual(len(prepared), 2)
        self.assertTrue(mail_folder.is_dir())
        linked_copy = local_services.resolve_portable_path(
            attachments[0]["stored_path"]
        )
        self.assertTrue(mark_order_sent(self.database, order_id))
        self.assertFalse(mail_folder.exists())
        self.assertTrue(pdf_path.is_file())
        self.assertTrue(linked_copy.is_file())
        sent_order, _ = self.database.get_order(order_id)
        self.assertEqual(sent_order["status"], "Envoyée")
        self.assertTrue(sent_order["sent_at"])

        backup = create_complete_backup(
            self.database, self.root / "sauvegarde.zip"
        )
        with zipfile.ZipFile(backup) as archive:
            names = archive.namelist()
        self.assertIn("data/commandes_cahpp.sqlite3", names)
        self.assertTrue(any(name.startswith("documents/") for name in names))

        remove_document(self.database, attachment_id)
        self.assertEqual(self.database.list_order_attachments(order_id), [])

        original_order, _ = self.database.get_order(order_id)
        edited_lines = [
            {
                "product_id": products[0]["id"],
                "code_cahpp": products[0]["code_cahpp"],
                "supplier_ref": products[0]["supplier_ref"],
                "designation": products[0]["designation"],
                "cartons": 3,
                "units_per_carton": products[0]["conditionnement"],
                "unit_price": products[0]["unit_price"],
                "vat": products[0]["vat"],
            }
        ]
        edited_order_id = self.database.save_order(
            supplier_id,
            edited_lines,
            notes="Brouillon modifié",
            order_id=order_id,
        )
        edited_order, edited_order_lines = self.database.get_order(edited_order_id)
        self.assertEqual(edited_order_id, order_id)
        self.assertEqual(
            edited_order["order_number"], original_order["order_number"]
        )
        self.assertEqual(edited_order_lines[0]["cartons"], 3)
        self.assertEqual(edited_order["notes"], "Brouillon modifié")

        self.database.save_settings(
            {
                "pdf_title": "COMMANDE FOURNISSEUR",
                "pdf_footer_text": "Document interne",
                "pdf_show_page_number": "0",
            }
        )
        custom_pdf = generate_order_pdf(
            self.database, order_id, self.root / "bon-personnalise.pdf"
        )
        custom_text = "\n".join(
            page.extract_text() or "" for page in PdfReader(custom_pdf).pages
        )
        self.assertIn("COMMANDE FOURNISSEUR", custom_text)
        self.assertIn("Document interne", custom_text)
        self.assertNotIn("Page 1", custom_text)

        second_path = self.root / "catalogue-2.xlsx"
        create_catalog(
            second_path,
            [
                self.row("DM001", "REF-A", "COMPRESSE TEST", 0.14, 120),
                self.row("DM003", "REF-C", "PANSEMENT TEST", 0.50, 20),
            ],
        )
        second = CatalogImporter(self.database).import_file(second_path)
        self.assertEqual(second.added_count, 1)
        self.assertEqual(second.updated_count, 1)
        self.assertEqual(second.missing_count, 1)
        self.assertEqual(
            float(self.database.search_products("REF-A")[0]["unit_price"]), 0.14
        )
        ordered_changes = self.database.ordered_changes_for_import(
            second.import_id
        )
        changed = next(
            row for row in ordered_changes if row["supplier_ref"] == "REF-A"
        )
        self.assertEqual(float(changed["old_price"]), 0.12)
        self.assertEqual(float(changed["new_price"]), 0.14)
        self.assertEqual(float(changed["old_pack"]), 100)
        self.assertEqual(float(changed["new_pack"]), 120)
        old_product = self.database.search_products(
            "REF-B", include_inactive=True
        )[0]
        self.assertEqual(old_product["active"], 0)
        backup_path = self.database.backup(self.root / "backup.sqlite3")
        self.assertTrue(backup_path.is_file())
        self.assertEqual(
            Database(backup_path).dashboard_stats()["products"], 2
        )

    def test_migration_from_version_04(self):
        path = self.root / "ancienne.sqlite3"
        connection = sqlite3.connect(path)
        connection.executescript(
            """
            CREATE TABLE suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cahpp_id INTEGER,
                name TEXT NOT NULL UNIQUE,
                customer_number TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                franco_ht REAL,
                notes TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_number TEXT NOT NULL UNIQUE,
                supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
                order_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Brouillon',
                notes TEXT NOT NULL DEFAULT '',
                total_ht REAL NOT NULL DEFAULT 0,
                total_vat REAL NOT NULL DEFAULT 0,
                total_ttc REAL NOT NULL DEFAULT 0,
                pdf_path TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        connection.close()
        migrated = Database(path)
        with migrated.connect() as connection:
            supplier_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(suppliers)")
            }
            order_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(orders)")
            }
            tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        self.assertTrue(
            {"contact_name", "address", "website", "minimum_order_ht"}
            <= supplier_columns
        )
        self.assertTrue({"email_prepared_at", "sent_at"} <= order_columns)
        self.assertIn("product_overrides", tables)
        self.assertTrue(migrated.get_settings()["mail_compose_url"])
        self.assertEqual(version, 8)

    def test_product_edits_dates_and_mail_variables(self):
        catalog_path = self.root / "catalogue.xlsx"
        create_catalog(
            catalog_path,
            [self.row("DM100", "REF-100", "ARTICLE CAHPP", 1.25, 50)],
        )
        CatalogImporter(self.database).import_file(catalog_path)
        product = self.database.search_products("DM100")[0]
        supplier_id = int(product["supplier_id"])

        self.database.set_product_override(
            int(product["id"]),
            supplier_ref="REF-CORRIGEE",
            designation="ARTICLE CORRIGÉ",
            conditionnement=24,
            unit_packaging="Boîte de 24",
            unit_price=1.10,
            vat=5.5,
        )
        corrected = self.database.get_product(int(product["id"]))
        self.assertTrue(corrected["has_override"])
        self.assertEqual(corrected["supplier_ref"], "REF-CORRIGEE")
        self.assertEqual(corrected["catalog_supplier_ref"], "REF-100")
        self.assertEqual(float(corrected["conditionnement"]), 24)
        self.assertEqual(
            self.database.search_products("CORRIGÉE")[0]["id"], product["id"]
        )

        updated_catalog = self.root / "catalogue-2.xlsx"
        create_catalog(
            updated_catalog,
            [self.row("DM100", "REF-NEW", "ARTICLE CAHPP NOUVEAU", 1.50, 60)],
        )
        CatalogImporter(self.database).import_file(updated_catalog)
        after_import = self.database.get_product(int(product["id"]))
        self.assertEqual(after_import["supplier_ref"], "REF-CORRIGEE")
        self.assertEqual(after_import["catalog_supplier_ref"], "REF-NEW")
        self.assertEqual(float(after_import["conditionnement"]), 24)

        self.database.reset_product_override(int(product["id"]))
        reset = self.database.get_product(int(product["id"]))
        self.assertFalse(reset["has_override"])
        self.assertEqual(reset["supplier_ref"], "REF-NEW")
        self.assertEqual(float(reset["conditionnement"]), 60)

        local_id = self.database.create_manual_product(
            supplier_id,
            "LOCAL-REF",
            "ARTICLE LOCAL",
            10,
            2.0,
            20,
        )
        self.database.update_manual_product(
            local_id,
            supplier_ref="LOCAL-MOD",
            designation="ARTICLE LOCAL MODIFIÉ",
            conditionnement=12,
            unit_packaging="Carton de 12",
            unit_price=2.5,
            vat=10,
        )
        local_product = self.database.get_product(local_id)
        self.assertEqual(local_product["supplier_ref"], "LOCAL-MOD")
        self.assertEqual(float(local_product["conditionnement"]), 12)
        self.database.archive_manual_product(local_id)
        self.assertEqual(self.database.get_product(local_id)["active"], 0)
        self.assertEqual(self.database.search_products("LOCAL-MOD"), [])

        self.database.update_supplier(
            supplier_id,
            customer_number="CLIENT-8",
            email="commandes@example.test",
            phone="",
            franco_ht=None,
            notes="",
        )
        order_id = self.database.save_order(
            supplier_id,
            [
                {
                    "product_id": reset["id"],
                    "code_cahpp": reset["code_cahpp"],
                    "supplier_ref": reset["supplier_ref"],
                    "designation": reset["designation"],
                    "cartons": 1,
                    "units_per_carton": reset["conditionnement"],
                    "unit_price": reset["unit_price"],
                    "vat": reset["vat"],
                }
            ],
        )
        order, _ = self.database.get_order(order_id)
        self.assertTrue(order["created_at"])
        with self.database.session() as connection:
            connection.execute(
                "UPDATE orders SET sent_at = '2026-01-02T03:04:05' WHERE id = ?",
                (order_id,),
            )
        self.assertFalse(mark_order_sent(self.database, order_id))
        sent_order, _ = self.database.get_order(order_id)
        self.assertEqual(sent_order["sent_at"], "2026-01-02T03:04:05")

        pdf_path = generate_order_pdf(
            self.database, order_id, self.root / "commande-mail.pdf"
        )
        self.assertTrue(pdf_path.is_file())
        self.database.save_settings(
            {
                "mail_compose_url": "mailto:",
                "email_subject_template": (
                    "Commande {order_number} du {date} - {supplier}"
                ),
                "email_body_template": (
                    "{establishment_name} / {customer_number} / "
                    "{total_ht} / {total_ttc}"
                ),
                "establishment_name": "Clinique test",
            }
        )
        compose_url, _, prepared = prepare_mail_order(self.database, order_id)
        parsed = urlparse(compose_url)
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.scheme, "mailto")
        self.assertEqual(parsed.path, "commandes@example.test")
        self.assertIn(
            datetime.fromisoformat(order["order_date"]).strftime("%d/%m/%Y"),
            query["subject"][0],
        )
        self.assertIn("Clinique test", query["body"][0])
        self.assertEqual(len(prepared), 1)


if __name__ == "__main__":
    unittest.main()
