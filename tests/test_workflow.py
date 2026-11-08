from __future__ import annotations

import os
import queue
import sqlite3
import tempfile
import time
import unittest
import zipfile
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from openpyxl import Workbook, load_workbook
from PIL import Image
from pypdf import PdfReader

from cahpp_app.catalog_importer import CatalogImporter, EXPECTED_COLUMNS
from cahpp_app.catalog_search import LatestCatalogSearchWorker
from cahpp_app.collaboration import (
    CollaborationManager,
    ResourceLockedError,
)
from cahpp_app.database import Database, ProductSearchResult, SearchCancelled
from cahpp_app.diagnostics import build_diagnostic_report
from cahpp_app import local_services
from cahpp_app.local_services import (
    attach_document,
    create_complete_backup,
    delete_draft,
    delete_unsent_order,
    mark_order_sent,
    prepare_mail_order,
    remove_document,
)
from cahpp_app.pdf_export import generate_order_pdf
from cahpp_app.statistics_export import export_statistics_workbook
from cahpp_app.numbers import field_display_value


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
        self.database.update_attachment_properties(
            attachment_id,
            "Facture",
            True,
        )
        attachment = self.database.get_order_attachment(attachment_id)
        self.assertEqual(attachment["kind"], "Facture")
        self.assertTrue(attachment["include_in_email"])
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

        # Une commande envoyée doit rester figée : la correction se fait sur
        # une nouvelle commande issue de la duplication.
        with self.assertRaises(ValueError):
            self.database.save_order(supplier_id, [{"designation": "Interdit", "cartons": 1,
                "units_per_carton": 1, "unit_price": 1, "vat": 20}], order_id=order_id)
        order_id = self.database.duplicate_order(order_id)
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
            CREATE TABLE order_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                product_id INTEGER,
                code_cahpp TEXT NOT NULL DEFAULT '',
                supplier_ref TEXT NOT NULL DEFAULT '',
                designation TEXT NOT NULL,
                cartons REAL NOT NULL DEFAULT 0,
                units_per_carton REAL NOT NULL DEFAULT 0,
                total_units REAL NOT NULL DEFAULT 0,
                unit_price REAL NOT NULL DEFAULT 0,
                vat REAL NOT NULL DEFAULT 0,
                total_ht REAL NOT NULL DEFAULT 0,
                line_order INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE product_team_state (
                code_cahpp TEXT PRIMARY KEY,
                favorite INTEGER NOT NULL DEFAULT 0,
                usual_cartons REAL NOT NULL DEFAULT 1,
                short_name TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                updated_by TEXT NOT NULL DEFAULT ''
            );
            INSERT INTO suppliers(name) VALUES ('ANCIEN FOURNISSEUR');
            INSERT INTO orders(
                order_number, supplier_id, order_date, created_at, updated_at
            ) VALUES ('BC-2024-0001', 1, '2024-01-01', '2024-01-01', '2024-01-01');
            INSERT INTO order_lines(
                order_id, designation, total_units, line_order
            ) VALUES (1, 'ANCIEN ARTICLE', 10, 0);
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
            team_state_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(product_team_state)"
                )
            }
            tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            migrated_line_uid = connection.execute(
                "SELECT line_uid FROM order_lines WHERE id = 1"
            ).fetchone()[0]
        self.assertTrue(
            {"contact_name", "address", "website", "minimum_order_ht"}
            <= supplier_columns
        )
        self.assertTrue(
            {"email_prepared_at", "sent_at", "requester_service"}
            <= order_columns
        )
        self.assertTrue(
            {"internal_notes", "replacement_code_cahpp"}
            <= team_state_columns
        )
        self.assertIn("product_overrides", tables)
        migrated_settings = migrated.get_settings()
        self.assertTrue(migrated_settings["mail_compose_url"])
        self.assertEqual(migrated_settings["sync_interval_seconds"], "60")
        self.assertEqual(migrated_settings["pause_sync_while_editing"], "1")
        self.assertEqual(version, 15)
        self.assertTrue(migrated_line_uid)

    def test_supplier_contact_punctuation_is_preserved_and_repaired(self):
        self.assertEqual(
            field_display_value("email", "commande@exemple.fr", {"franco_ht"}),
            "commande@exemple.fr",
        )
        self.assertEqual(
            field_display_value("website", "www.exemple.fr", {"franco_ht"}),
            "www.exemple.fr",
        )
        self.assertEqual(
            field_display_value("franco_ht", 400.0, {"franco_ht"}),
            "400,0",
        )
        self.assertEqual(
            field_display_value("supplier_ref", "REF.123", {"unit_price"}),
            "REF.123",
        )
        self.assertEqual(
            field_display_value("unit_price", 12.5, {"unit_price"}),
            "12,5",
        )

        path = self.root / "fournisseurs-corrompus.sqlite3"
        damaged = Database(path)
        with damaged.session() as connection:
            connection.execute(
                """
                INSERT INTO suppliers(
                    name, contact_name, email, phone, website, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "FOURNISSEUR TEST",
                    "03,20,30,40,50 service,client@test,fr",
                    "commande@test,fr",
                    "03,20,30,40,50",
                    "www,test,fr",
                    "2026-08-01T10:00:00",
                ),
            )
            connection.execute("PRAGMA user_version = 13")

        repaired = Database(path)
        supplier = repaired.list_suppliers()[0]
        self.assertEqual(
            supplier["contact_name"],
            "03.20.30.40.50 service.client@test.fr",
        )
        self.assertEqual(supplier["email"], "commande@test.fr")
        self.assertEqual(supplier["phone"], "03.20.30.40.50")
        self.assertEqual(supplier["website"], "www.test.fr")
        with repaired.connect() as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                15,
            )

        repaired.apply_team_state(
            {
                "suppliers": {
                    "FOURNISSEUR SYNCHRONISÉ": {
                        "email": "commandes@fournisseur,fr",
                        "phone": "01,02,03,04,05",
                        "website": "www,fournisseur,fr",
                        "updated_at": "2026-08-04T12:00:00",
                        "updated_by": "Collègue",
                    }
                }
            }
        )
        synchronized = next(
            row
            for row in repaired.list_suppliers()
            if row["name"] == "FOURNISSEUR SYNCHRONISÉ"
        )
        self.assertEqual(synchronized["email"], "commandes@fournisseur.fr")
        self.assertEqual(synchronized["phone"], "01.02.03.04.05")
        self.assertEqual(synchronized["website"], "www.fournisseur.fr")

    def test_alerts_recommendations_filters_metrics_and_export(self):
        catalogue = self.root / "catalogue-v13.xlsx"
        create_catalog(
            catalogue,
            [
                self.row("V13-1", "REF-V13", "ARTICLE RÉCURRENT", 3, 10),
                self.row("V13-2", "REF-REMPL", "ARTICLE DE REMPLACEMENT", 4, 10),
            ],
        )
        CatalogImporter(self.database).import_file(catalogue)
        recurring = self.database.search_products("ARTICLE RÉCURRENT")[0]
        replacement = self.database.search_products("REMPLACEMENT")[0]
        self.database.update_product_team_details(
            int(recurring["id"]),
            internal_notes="Privilégier le nouveau conditionnement.",
            replacement_code_cahpp=str(replacement["code_cahpp"]),
        )

        order_ids = []
        for order_date in (date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)):
            order_id = self.database.save_order(
                int(recurring["supplier_id"]),
                [
                    {
                        "product_id": int(recurring["id"]),
                        "code_cahpp": recurring["code_cahpp"],
                        "supplier_ref": recurring["supplier_ref"],
                        "designation": recurring["designation"],
                        "cartons": 1,
                        "units_per_carton": 10,
                        "unit_price": 3,
                        "vat": 20,
                    }
                ],
                selected_date=order_date,
                requester_service="Unité protégée",
            )
            self.database.update_order_status(order_id, "Envoyée")
            order_ids.append(order_id)
        with self.database.session() as connection:
            connection.execute(
                """
                UPDATE orders
                SET sent_at = '2026-01-02T08:00:00',
                    confirmed_at = '2026-01-04T08:00:00',
                    delivered_at = '2026-01-10T08:00:00',
                    delivery_status = 'Livrée', status = 'Livrée'
                WHERE id = ?
                """,
                (order_ids[0],),
            )
        service_pdf = generate_order_pdf(
            self.database, order_ids[0], self.root / "commande-service.pdf"
        )
        service_text = "\n".join(
            page.extract_text() or "" for page in PdfReader(service_pdf).pages
        )
        self.assertIn("Unité protégée", service_text)
        suggestions = self.database.reorder_suggestions(date(2026, 4, 5))
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["product_id"], recurring["id"])

        _, first_lines = self.database.get_order(order_ids[0])
        duplicate_id = self.database.duplicate_order_lines(
            order_ids[0], [first_lines[0]["line_uid"]]
        )
        duplicate, duplicate_lines = self.database.get_order(duplicate_id)
        self.assertEqual(duplicate["requester_service"], "Unité protégée")
        self.assertEqual(len(duplicate_lines), 1)

        alert_id = self.database.save_order(
            int(recurring["supplier_id"]),
            [
                {
                    "product_id": int(recurring["id"]),
                    "code_cahpp": recurring["code_cahpp"],
                    "supplier_ref": recurring["supplier_ref"],
                    "designation": recurring["designation"],
                    "cartons": 1,
                    "units_per_carton": 10,
                    "unit_price": 3,
                    "vat": 20,
                }
            ],
            selected_date=date(2026, 7, 20),
        )
        self.database.update_order_status(alert_id, "Envoyée")
        with self.database.session() as connection:
            connection.execute(
                """
                UPDATE orders
                SET sent_at = '2026-07-20T08:00:00',
                    expected_delivery_date = '2026-07-25'
                WHERE id = ?
                """,
                (alert_id,),
            )
        alerts = self.database.order_alerts(
            date(2026, 8, 1), confirmation_days=5, delivery_days=14
        )
        self.assertEqual(
            {row["alert_type"] for row in alerts if row["id"] == alert_id},
            {"Confirmation attendue", "Livraison en retard"},
        )

        self.database.save_order_filter(
            "Retards Hartmann", "HARTMANN", "Tous", "À recevoir", False
        )
        filters = self.database.list_saved_order_filters()
        self.assertEqual(filters[0]["name"], "Retards Hartmann")
        self.database.delete_order_filter("Retards Hartmann")
        self.assertEqual(self.database.list_saved_order_filters(), [])

        self.database.set_product_override(
            int(recurring["id"]),
            supplier_ref=str(recurring["supplier_ref"]),
            designation=str(recurring["designation"]),
            conditionnement=10,
            unit_packaging="",
            unit_price=4,
            vat=20,
        )
        statistics = self.database.statistics(date(2026, 1, 1), date(2026, 12, 31))
        supplier_metrics = statistics["suppliers"][0]
        self.assertEqual(supplier_metrics["average_confirmation_days"], 2)
        self.assertEqual(supplier_metrics["average_delivery_days"], 8)
        self.assertTrue(statistics["price_variances"])
        export_path = export_statistics_workbook(
            statistics,
            date(2026, 1, 1),
            date(2026, 12, 31),
            self.root / "statistiques.xlsx",
        )
        self.assertTrue(export_path.is_file())
        workbook = load_workbook(export_path, read_only=True)
        try:
            self.assertEqual(workbook["Synthèse"]["B2"].value.date(), date(2026, 1, 1))
            self.assertEqual(workbook["Synthèse"]["B2"].number_format, "yyyy-mm-dd")
            self.assertTrue(workbook["Écarts de prix"]["E2"].is_date)
            self.assertEqual(
                workbook["Écarts de prix"]["E2"].number_format, "yyyy-mm-dd"
            )
        finally:
            workbook.close()
        with zipfile.ZipFile(export_path) as archive:
            workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        self.assertIn("Fournisseurs", workbook_xml)
        self.assertIn("Écarts de prix", workbook_xml)

        second_database = Database(self.root / "second-v13.sqlite3")
        CatalogImporter(second_database).import_file(catalogue)
        second_database.apply_team_state(self.database.export_team_state())
        synced = second_database.get_product(int(recurring["id"]))
        self.assertEqual(
            synced["internal_notes"], "Privilégier le nouveau conditionnement."
        )
        self.assertEqual(synced["replacement_code_cahpp"], replacement["code_cahpp"])
        imported_order_id, changed = second_database.import_order(
            self.database.export_order(order_ids[0])
        )
        self.assertTrue(changed)
        imported_order, _ = second_database.get_order(imported_order_id)
        self.assertEqual(imported_order["requester_service"], "Unité protégée")

    def test_partial_receipts_milestones_comments_and_sync(self):
        catalogue = self.root / "catalogue-receptions.xlsx"
        create_catalog(
            catalogue,
            [self.row("REC-1", "REF-REC", "ARTICLE À RÉCEPTIONNER", 3, 10)],
        )
        CatalogImporter(self.database).import_file(catalogue)
        product = self.database.search_products("RÉCEPTIONNER")[0]
        order_id = self.database.save_order(
            int(product["supplier_id"]),
            [
                {
                    "product_id": int(product["id"]),
                    "code_cahpp": product["code_cahpp"],
                    "supplier_ref": product["supplier_ref"],
                    "designation": product["designation"],
                    "cartons": 2,
                    "units_per_carton": 10,
                    "unit_price": 3,
                    "vat": 20,
                }
            ],
        )
        self.database.update_order_status(order_id, "Envoyée")
        self.database.mark_order_confirmed(
            order_id, expected_delivery_date=date(2026, 8, 10)
        )
        self.database.add_order_comment(order_id, "Livraison annoncée le matin.")
        summary = self.database.receipt_summary(order_id)
        line_uid = str(summary["lines"][0]["line_uid"])
        first_receipt = self.database.add_receipt(
            order_id,
            date(2026, 8, 8),
            {line_uid: 7},
            reference="BL-001",
        )
        partial = self.database.receipt_summary(order_id)
        self.assertEqual(partial["order"]["delivery_status"], "Partiellement livrée")
        self.assertEqual(partial["order"]["status"], "Partiellement livrée")
        self.assertEqual(partial["lines"][0]["received_units"], 7)
        self.assertEqual(partial["lines"][0]["remaining_units"], 13)
        self.assertEqual(self.database.dashboard_stats()["pending_deliveries"], 1)

        second_receipt = self.database.add_receipt(
            order_id,
            date(2026, 8, 9),
            {line_uid: 13},
            reference="BL-002",
        )
        delivered = self.database.receipt_summary(order_id)
        self.assertEqual(delivered["order"]["delivery_status"], "Livrée")
        self.assertEqual(delivered["lines"][0]["remaining_units"], 0)
        self.database.mark_order_invoiced(order_id)
        invoiced, _ = self.database.get_order(order_id)
        self.assertEqual(invoiced["status"], "Facturée")

        shared = self.root / "partage-receptions"
        first_manager = CollaborationManager(
            self.database, "user-1", "Damien", shared
        )
        first_manager.initialize_workspace()
        first_manager.publish_order(order_id)
        second_database = Database(self.root / "receptions-second.sqlite3")
        second_manager = CollaborationManager(
            second_database, "user-2", "Collègue", shared
        )
        second_manager.initialize_workspace()
        self.assertEqual(second_manager.sync_orders()["imported"], 1)
        received_order = second_database.list_orders()[0]
        received_summary = second_database.receipt_summary(int(received_order["id"]))
        self.assertEqual(len(received_summary["receipts"]), 2)
        self.assertEqual(received_summary["lines"][0]["received_units"], 20)
        self.assertEqual(
            second_database.list_order_comments(int(received_order["id"]))[0]["body"],
            "Livraison annoncée le matin.",
        )

        self.database.delete_receipt(second_receipt)
        corrected = self.database.receipt_summary(order_id)
        self.assertEqual(corrected["order"]["delivery_status"], "Partiellement livrée")
        self.assertEqual(corrected["lines"][0]["remaining_units"], 13)
        self.assertEqual(first_receipt, 1)

    def test_delivery_statistics_archive_and_installer(self):
        catalogue = self.root / "catalogue-suivi.xlsx"
        create_catalog(
            catalogue,
            [self.row("SUIVI-1", "REF-SUIVI", "ARTICLE SUIVI", 2.5, 10)],
        )
        CatalogImporter(self.database).import_file(catalogue)
        supplier_id = int(self.database.list_suppliers()[0]["id"])
        product = self.database.search_products(query="ARTICLE SUIVI")[0]
        order_id = self.database.save_order(
            supplier_id,
            [
                {
                    "product_id": int(product["id"]),
                    "code_cahpp": product["code_cahpp"],
                    "supplier_ref": product["supplier_ref"],
                    "designation": product["designation"],
                    "cartons": 2,
                    "units_per_carton": 10,
                    "unit_price": 2.5,
                    "vat": 20,
                }
            ],
            selected_date=date(2024, 1, 15),
        )
        self.database.update_order_status(order_id, "Envoyée")
        order, _ = self.database.get_order(order_id)
        self.assertEqual(order["delivery_status"], "En attente")
        self.assertEqual(self.database.dashboard_stats()["pending_deliveries"], 1)

        statistics = self.database.statistics(
            date(2024, 1, 1), date(2024, 12, 31)
        )
        self.assertEqual(statistics["summary"]["order_count"], 1)
        self.assertEqual(statistics["summary"]["total_ht"], 50)
        self.assertEqual(statistics["suppliers"][0]["supplier_name"], "HARTMANN")
        self.assertEqual(statistics["products"][0]["total_units"], 20)

        self.database.update_delivery_status(order_id, "Livrée")
        archived = self.database.archive_old_orders(date(2025, 1, 1))
        self.assertEqual(archived, [order_id])
        self.assertEqual(self.database.list_orders(), [])
        archived_orders = self.database.list_orders(include_archived=True)
        self.assertEqual(len(archived_orders), 1)
        self.assertTrue(archived_orders[0]["archived_at"])

        shared = self.root / "partage-mises-a-jour"
        manager = CollaborationManager(
            self.database, "user-1", "Damien", shared
        )
        manager.initialize_workspace()
        second_database = Database(self.root / "second-suivi.sqlite3")
        second_database.set_current_user("user-2", "Collègue")
        second = CollaborationManager(
            second_database, "user-2", "Collègue", shared
        )
        second.initialize_workspace()
        manager.publish_order(order_id)
        self.assertEqual(second.sync_orders()["imported"], 1)
        received = second_database.list_orders(include_archived=True)[0]
        self.assertEqual(received["delivery_status"], "Livrée")
        self.assertTrue(received["archived_at"])
        installer = manager.updates_dir / "CommandesCAHPP-Setup-1.2.0.exe"
        installer.write_bytes(b"installer-test")
        pending = manager.pending_installer("1.1.0")
        self.assertIsNotNone(pending)
        self.assertEqual(pending["version"], "1.2.0")
        self.assertIsNone(manager.pending_installer("1.1.0", "1.2.0"))
        self.assertEqual(self.database.quick_integrity_check(), (True, "ok"))

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
            "1.1.0",
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

    def test_delete_generated_and_email_prepared_orders_syncs(self):
        catalog = self.root / "deletion.xlsx"
        create_catalog(catalog, [self.row("DEL1", "REF-DEL", "ARTICLE TEST", 1)])
        CatalogImporter(self.database).import_file(catalog)
        other = Database(self.root / "other.sqlite3")
        CatalogImporter(other).import_file(catalog)
        shared = self.root / "shared"
        first = CollaborationManager(self.database, "a", "Damien", shared)
        second = CollaborationManager(other, "b", "Collègue", shared)
        first.initialize_workspace()
        second.initialize_workspace()
        product = self.database.search_products("article")[0]
        for prepared in (False, True):
            with self.subTest(prepared=prepared):
                order_id = self.database.save_order(
                    product["supplier_id"],
                    [{"product_id": product["id"], "designation": "ARTICLE TEST",
                      "cartons": 1, "units_per_carton": 100,
                      "unit_price": 1, "vat": 20}],
                    order_number=first.reserve_order_number(),
                )
                pdf = generate_order_pdf(self.database, order_id,
                                         self.root / f"export-{order_id}.pdf")
                attachment_id = attach_document(self.database, order_id, pdf, "Devis")
                attachment = local_services.resolve_portable_path(
                    self.database.get_order_attachment(attachment_id)["stored_path"]
                )
                staging = local_services.MAIL_PREP_DIR / local_services.safe_filename(
                    self.database.get_order(order_id)[0]["order_number"]
                )
                staging.mkdir(parents=True)
                if prepared:
                    self.database.update_order_status(order_id, "E-mail préparé")
                first.publish_order(order_id)
                second.sync_orders()
                self.assertEqual(len(other.list_orders()), 1)
                with first.acquire_lock("commande", str(
                    self.database.get_order(order_id)[0]["shared_uid"]
                )):
                    delete_unsent_order(self.database, order_id)
                    first.publish_order(order_id)
                second.sync_orders()
                self.assertEqual(self.database.list_orders(), [])
                self.assertEqual(other.list_orders(), [])
                self.assertFalse(attachment.exists())
                self.assertFalse(staging.exists())
                self.assertTrue(pdf.is_file())  # Le PDF exporté appartient à l'utilisateur.
                deleted, lines = self.database.get_order(order_id)
                self.assertTrue(deleted["deleted_at"])
                self.assertEqual(lines, [])
                with self.assertRaises(ValueError):
                    delete_unsent_order(self.database, order_id)

    def test_delete_unsent_order_refuses_sent_or_followed_orders(self):
        catalog = self.root / "protected.xlsx"
        create_catalog(catalog, [self.row("DEL2", "REF-DEL", "ARTICLE TEST", 1)])
        CatalogImporter(self.database).import_file(catalog)
        product = self.database.search_products("article")[0]
        protections = [
            {"status": "Envoyée"},
            {"status": "Générée", "sent_at": "2026-11-05T09:00:00"},
            {"confirmed_at": "2026-11-05T09:00:00"},
            {"invoiced_at": "2026-11-05T09:00:00"},
            {"delivery_status": "Partiellement livrée"},
            {"status": "Livrée"},
        ]
        for fields in protections:
            with self.subTest(fields=fields):
                order_id = self.database.save_order(
                    product["supplier_id"],
                    [{"designation": "ARTICLE TEST", "cartons": 1,
                      "units_per_carton": 1, "unit_price": 1, "vat": 20}],
                )
                with self.database.session() as connection:
                    connection.execute(
                        "UPDATE orders SET " + ", ".join(f"{key} = ?" for key in fields)
                        + " WHERE id = ?", [*fields.values(), order_id],
                    )
                before, lines = self.database.get_order(order_id)
                with self.assertRaises(ValueError):
                    delete_unsent_order(self.database, order_id)
                after, remaining = self.database.get_order(order_id)
                self.assertEqual(dict(before), dict(after))
                self.assertEqual(len(lines), len(remaining))

    def test_catalog_search_repairs_incomplete_fts_index(self):
        catalog = self.root / "catalogue-recherche.xlsx"
        create_catalog(
            catalog,
            [
                self.row("DM100", "REF-100", "GANT NITRILE", 0.08),
                self.row("DM101", "REF-101", "COMPRESSE STERILE", 0.12),
            ],
        )
        CatalogImporter(self.database).import_file(catalog)
        status = self.database.search_index_status()
        self.assertTrue(status["consistent"])
        with self.database.session() as connection:
            connection.execute(
                "DELETE FROM product_search WHERE rowid = "
                "(SELECT id FROM products WHERE code_cahpp = 'DM100')"
            )
        self.database._fts_verified = False

        result = self.database.search_products_detailed("gant")

        self.assertEqual([row["code_cahpp"] for row in result.rows], ["DM100"])
        self.assertEqual(result.mode, "fts5")
        self.assertTrue(result.repaired)
        self.assertTrue(self.database.search_index_status()["consistent"])

    def test_catalog_search_recreates_missing_fts_table(self):
        catalog = self.root / "catalogue-index-absent.xlsx"
        create_catalog(
            catalog,
            [self.row("DM200", "REF-200", "MASQUE CHIRURGICAL", 0.04)],
        )
        CatalogImporter(self.database).import_file(catalog)
        with self.database.session() as connection:
            connection.execute("DROP TABLE product_search")
        self.database._fts_verified = False

        result = self.database.search_products_detailed("masque")

        self.assertEqual(len(result.rows), 1)
        self.assertTrue(result.repaired)
        self.assertTrue(self.database.search_index_status()["consistent"])

    def test_latest_catalog_search_worker_discards_obsolete_request(self):
        class SlowDatabase:
            def search_products_detailed(
                self,
                query,
                supplier_id,
                favorite_only,
                limit,
                allow_slow_fallback,
                cancel_event,
            ):
                if query == "ancienne":
                    for _ in range(100):
                        if cancel_event.is_set():
                            raise SearchCancelled()
                        time.sleep(0.002)
                return ProductSearchResult(
                    rows=[{"query": query}],
                    mode="fts5",
                    elapsed_ms=1,
                )

        outcomes = queue.Queue()
        worker = LatestCatalogSearchWorker(SlowDatabase(), outcomes.put)
        try:
            worker.submit(
                query="ancienne",
                supplier_id=None,
                favorite_only=False,
                limit=101,
                allow_slow_fallback=False,
            )
            time.sleep(0.01)
            latest = worker.submit(
                query="nouvelle",
                supplier_id=None,
                favorite_only=False,
                limit=101,
                allow_slow_fallback=False,
            )
            outcome = outcomes.get(timeout=2)
        finally:
            worker.close()
        self.assertEqual(outcome.generation, latest)
        self.assertEqual(outcome.result.rows, [{"query": "nouvelle"}])


if __name__ == "__main__":
    unittest.main()
