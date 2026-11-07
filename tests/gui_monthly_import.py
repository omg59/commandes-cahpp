"""Vrai parcours Tk : annuler, importer un delta, vérifier puis commander un article."""

from __future__ import annotations

import tkinter as tk
from unittest.mock import patch

from cahpp_app.catalog_importer import CatalogImporter
from cahpp_app.database import Database
from cahpp_app.paths import DATABASE_PATH, ROOT_DIR
from cahpp_app.ui import App, ProductEditDialog
from tests.gui_roundtrip import wait
from tests.test_monthly_catalog import create_monthly, monthly_row
from tests.test_workflow import create_catalog


def main():
    db = Database(DATABASE_PATH)
    db.save_settings(
        {"user_name": "Test", "user_id": "test", "collaboration_enabled": "0"}
    )
    base = ROOT_DIR / "base.xlsx"
    create_catalog(
        base,
        [
            {
                "Catalogue": "DM",
                "IDFournisseur": 11020,
                "NomFournisseur": "HARTMANN",
                "CodeCahpp": code,
                "RéférenceArticle": code,
                "DésignationArticle": "ARTICLE " + code,
                "Conditionnement": 10,
                "Qml": 10,
                "PrixUnitaireCahpp": 1,
                "TVA": 20,
            }
            for code in ("DM001", "TEMOIN")
        ],
    )
    CatalogImporter(db).import_file(base)
    monthly = ROOT_DIR / "novembre.xlsx"
    create_monthly(
        monthly,
        [monthly_row(), monthly_row("DM005", kind="ANR", state="NOUVELLE REFERENCE")],
    )
    root = tk.Tk()
    errors = []
    root.report_callback_exception = lambda *args: errors.append(args)
    with (
        patch.object(App, "_start_background_maintenance"),
        patch.object(App, "_offer_shared_installer"),
        patch("tkinter.messagebox.showinfo"),
        patch("tkinter.messagebox.showerror") as error_box,
        patch("tkinter.messagebox.showwarning") as warning_box,
    ):
        app = App(root, db)
        try:
            app.show_page("import")
            page = app.pages["import"]
            page.path_var.set(str(monthly))
            with patch("tkinter.messagebox.askyesno", return_value=False):
                page.start_import()
                wait(
                    root,
                    lambda: (
                        not page.worker.is_alive()
                        and str(page.import_button["state"]) == "normal"
                    ),
                )
            assert len(db.latest_imports()) == 1
            assert "annulé" in page.status_label["text"]
            with (
                patch("tkinter.messagebox.askyesno", return_value=True),
                patch(
                    "cahpp_app.ui.import_catalog.create_complete_backup",
                    side_effect=OSError("disque plein"),
                ),
            ):
                page.start_import()
                wait(
                    root,
                    lambda: (
                        not page.worker.is_alive()
                        and str(page.import_button["state"]) == "normal"
                    ),
                )
            error_box.assert_called_once()
            error_box.reset_mock()
            assert len(db.latest_imports()) == 1
            with patch("tkinter.messagebox.askyesno", return_value=True) as confirm:
                page.start_import()
                wait(
                    root,
                    lambda: (
                        not page.worker.is_alive()
                        and str(page.import_button["state"]) == "normal"
                    ),
                )
                assert "Évolutions mensuelles" in confirm.call_args.args[1]
            assert len(db.latest_imports()) == 2
            assert db.get_settings()["catalog_effective_period"] == "2026-11"
            from pathlib import Path
            from zipfile import ZipFile

            backup = Path(db.get_settings()["last_backup_path"])
            with ZipFile(backup) as archive:
                assert archive.testzip() is None
                assert "data/commandes_cahpp.sqlite3" in archive.namelist()
            app.show_page("catalog")
            catalog = app.pages["catalog"]
            catalog.review_only_var.set(True)
            catalog.search(force=True)
            wait(
                root,
                lambda: (
                    not catalog._search_pending and catalog._render_after_id is None
                ),
            )
            ids = catalog.tree.get_children()
            assert len(ids) == 1
            product_id = int(ids[0])
            assert db.get_product(product_id)["code_cahpp"] == "DM005"
            app.show_page("new_order")
            order = app.pages["new_order"]
            order.supplier_var.set("HARTMANN")
            order.supplier_changed()
            order.add_product_by_id(product_id)
            assert not order.cart
            warning_box.assert_called_once()
            warning_box.reset_mock()
            dialog = ProductEditDialog(root, db, product_id)
            root.update()
            assert dialog.save_button.winfo_ismapped()
            assert (
                dialog.save_button.winfo_rooty() + dialog.save_button.winfo_height()
                <= dialog.winfo_rooty() + dialog.winfo_height()
            )
            dialog.vars["conditionnement"].set("12")
            dialog.save()
            error_box.assert_called_once()
            error_box.reset_mock()
            assert not dialog.saved
            dialog.review_confirmed_var.set(True)
            dialog.save()
            assert dialog.saved
            assert not db.get_product(product_id)["catalog_review_required"]
            with patch("tkinter.simpledialog.askfloat", return_value=2):
                order.add_product_by_id(product_id)
            assert order.cart[0]["units_per_carton"] == 12
            with patch("tkinter.messagebox.askyesno", return_value=True):
                assert order.save_draft()
            saved, lines = db.get_order(db.list_orders()[0]["id"])
            assert saved["status"] == "Brouillon" and lines[0]["total_units"] == 24
            error_box.assert_not_called()
            warning_box.assert_not_called()
            assert not errors, repr(errors)
        finally:
            app.close(force=True)


if __name__ == "__main__":
    main()
