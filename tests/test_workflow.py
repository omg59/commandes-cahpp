from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook
from pypdf import PdfReader

from cahpp_app.catalog_importer import CatalogImporter, EXPECTED_COLUMNS
from cahpp_app.database import Database
from cahpp_app.pdf_export import generate_order_pdf
from cahpp_app.ui import (
    configured_pdf_directory,
    filter_supplier_names,
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
        self.database = Database(self.root / "test.sqlite3")

    def tearDown(self):
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
        )
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
        self.assertNotIn(
            "Bon de commande généré localement avec Commandes CAHPP",
            pdf_text,
        )

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
        old_product = self.database.search_products(
            "REF-B", include_inactive=True
        )[0]
        self.assertEqual(old_product["active"], 0)
        backup_path = self.database.backup(self.root / "backup.sqlite3")
        self.assertTrue(backup_path.is_file())
        self.assertEqual(
            Database(backup_path).dashboard_stats()["products"], 2
        )


if __name__ == "__main__":
    unittest.main()
