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
from cahpp_app.collaboration import (
    CollaborationManager,
    ResourceLockedError,
)
from cahpp_app.database import Database
from cahpp_app.diagnostics import build_diagnostic_report
from cahpp_app import local_services
from cahpp_app.local_services import (
    attach_document,
    create_complete_backup,
    delete_draft,
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
        self.assertNotIn("Franco non atteint", pdf_text)
        self.assertNotIn("Franco atteint", pdf_text)

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
        migrated_settings = migrated.get_settings()
        self.assertTrue(migrated_settings["mail_compose_url"])
        self.assertEqual(migrated_settings["sync_interval_seconds"], "60")
        self.assertEqual(migrated_settings["pause_sync_while_editing"], "1")
        self.assertEqual(version, 10)

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

    def test_collaboration_without_server(self):
        shared = self.root / "partage"
        second_database = Database(self.root / "second.sqlite3")
        self.database.set_current_user("user-damien", "Damien")
        second_database.set_current_user("user-sophie", "Sophie")

        catalogue = self.root / "catalogue-collaboratif.xlsx"
        create_catalog(
            catalogue,
            [
                self.row("DM001", "REF-A", "COMPRESSE TEST", 0.12, 100),
                self.row("DM002", "REF-B", "GANT TEST", 0.03, 1000),
            ],
        )
        first_result = CatalogImporter(self.database).import_file(catalogue)
        CatalogImporter(second_database).import_file(catalogue)

        first = CollaborationManager(
            self.database, "user-damien", "Damien", shared
        )
        second = CollaborationManager(
            second_database, "user-sophie", "Sophie", shared
        )
        workspace_id = first.initialize_workspace()
        self.assertEqual(second.initialize_workspace(), workspace_id)

        product = self.database.search_products("compresse")[0]
        supplier_id = int(product["supplier_id"])
        self.database.update_supplier(
            supplier_id,
            customer_number="CLIENT-COMMUN",
            email="commandes@example.test",
            phone="",
            franco_ht=250,
            notes="Paramètre partagé",
        )
        self.database.set_favorite(
            int(product["id"]),
            True,
            usual_cartons=3,
            short_name="Compresse favorite",
        )
        self.database.set_product_override(
            int(product["id"]),
            supplier_ref="REF-CORRIGEE",
            designation="COMPRESSE CORRIGEE",
            conditionnement=120,
            unit_packaging="12 x 10",
            unit_price=0.13,
            vat=20,
        )
        manual_id = self.database.create_manual_product(
            supplier_id,
            "LOCAL-REF",
            "ARTICLE LOCAL PARTAGE",
            10,
            1.5,
            20,
            "Boîte de 10",
        )
        first.sync_team_state()
        second.sync_team_state()

        second_product = second_database.search_products("corrigee")[0]
        self.assertEqual(second_product["supplier_ref"], "REF-CORRIGEE")
        self.assertEqual(second_product["conditionnement"], 120)
        self.assertEqual(second_product["usual_cartons"], 3)
        self.assertTrue(second_product["favorite"])
        self.assertEqual(
            second_database.search_products("article local partage")[0][
                "supplier_ref"
            ],
            "LOCAL-REF",
        )
        second_supplier = second_database.get_supplier(
            int(second_product["supplier_id"])
        )
        self.assertEqual(second_supplier["customer_number"], "CLIENT-COMMUN")

        order_number = first.reserve_order_number()
        order_id = self.database.save_order(
            supplier_id,
            [
                {
                    "product_id": manual_id,
                    "code_cahpp": self.database.get_product(manual_id)[
                        "code_cahpp"
                    ],
                    "supplier_ref": "LOCAL-REF",
                    "designation": "ARTICLE LOCAL PARTAGE",
                    "cartons": 2,
                    "units_per_carton": 10,
                    "unit_price": 1.5,
                    "vat": 20,
                }
            ],
            notes="Commande collaborative",
            order_number=order_number,
        )
        generated_pdf = generate_order_pdf(
            self.database, order_id, self.root / "bc-collaboratif.pdf"
        )
        linked_document = self.root / "bon-livraison-collaboratif.pdf"
        linked_document.write_bytes(b"%PDF-1.4\n% document partage\n")
        attach_document(
            self.database,
            order_id,
            linked_document,
            "Bon de livraison",
        )
        first.publish_order(order_id)
        sync_result = second.sync_orders()
        self.assertEqual(sync_result["imported"], 1)
        imported_order = second_database.list_orders()[0]
        self.assertEqual(imported_order["order_number"], order_number)
        self.assertEqual(imported_order["created_by"], "Damien")
        self.assertFalse(str(imported_order["pdf_path"]).startswith("shared:"))
        self.assertTrue(
            local_services.resolve_portable_path(
                imported_order["pdf_path"]
            ).is_file()
        )
        imported_attachments = second_database.list_order_attachments(
            int(imported_order["id"])
        )
        self.assertEqual(len(imported_attachments), 1)
        self.assertTrue(
            local_services.resolve_portable_path(
                imported_attachments[0]["stored_path"]
            ).is_file()
        )
        self.assertTrue(generated_pdf.is_file())

        order, _ = self.database.get_order(order_id)
        with first.acquire_lock("commande", order["shared_uid"]):
            with self.assertRaises(ResourceLockedError):
                second.acquire_lock("commande", order["shared_uid"])
        stale_lock = first.acquire_lock(
            "produit", "VERROU-EXPIRE", ttl_seconds=-1
        )
        self.assertEqual(second.cleanup_expired_locks(), 1)
        stale_lock.release()

        first.publish_catalog(catalogue, first_result)
        pending = second.pending_catalog()
        self.assertIsNotNone(pending)
        shared_source = second.catalog_source(pending)
        duplicate = CatalogImporter(second_database).import_file(shared_source)
        self.assertTrue(duplicate.already_imported)
        second.mark_catalog_applied(pending)
        self.assertIsNone(second.pending_catalog())

        report = build_diagnostic_report(
            second_database,
            second,
            "1.0.0-rc3",
            {
                "synced_at": "2026-07-29T08:00:00",
                "orders": sync_result,
                "catalog_pending": False,
            },
        )
        self.assertIn("Contrôle d'intégrité : OK", report)
        self.assertIn("Identifiant cohérent : OK", report)
        self.assertIn(f"Commandes partagées : 1", report)
        self.assertNotIn("ARTICLE LOCAL PARTAGE", report)

        draft_number = first.reserve_order_number()
        draft_id = self.database.save_order(
            supplier_id,
            [
                {
                    "product_id": manual_id,
                    "code_cahpp": self.database.get_product(manual_id)[
                        "code_cahpp"
                    ],
                    "supplier_ref": "LOCAL-REF",
                    "designation": "ARTICLE LOCAL PARTAGE",
                    "cartons": 1,
                    "units_per_carton": 10,
                    "unit_price": 1.5,
                    "vat": 20,
                }
            ],
            notes="Brouillon à supprimer",
            order_number=draft_number,
        )
        draft_document = self.root / "piece-brouillon.pdf"
        draft_document.write_bytes(b"%PDF-1.4\n% brouillon\n")
        draft_attachment_id = attach_document(
            self.database,
            draft_id,
            draft_document,
            "Pièce jointe e-mail",
        )
        local_draft_copy = local_services.resolve_portable_path(
            self.database.get_order_attachment(draft_attachment_id)[
                "stored_path"
            ]
        )
        first.publish_order(draft_id)
        second.sync_orders()
        imported_draft = next(
            row
            for row in second_database.list_orders()
            if row["order_number"] == draft_number
        )
        remote_attachment = second_database.list_order_attachments(
            int(imported_draft["id"])
        )[0]
        remote_cached_copy = local_services.resolve_portable_path(
            remote_attachment["stored_path"]
        )
        self.assertTrue(remote_cached_copy.is_file())

        delete_draft(self.database, draft_id)
        self.assertFalse(local_draft_copy.exists())
        first.publish_order(draft_id)
        second.sync_orders()
        self.assertNotIn(
            draft_number,
            [row["order_number"] for row in second_database.list_orders()],
        )
        with second_database.connect() as connection:
            deleted = connection.execute(
                "SELECT deleted_at, deleted_by FROM orders WHERE order_number = ?",
                (draft_number,),
            ).fetchone()
        self.assertTrue(deleted["deleted_at"])
        self.assertEqual(deleted["deleted_by"], "Damien")
        self.assertFalse(remote_cached_copy.exists())
        with self.assertRaises(ValueError):
            self.database.delete_draft(order_id)


if __name__ == "__main__":
    unittest.main()
