"""Scénario graphique exécuté dans un processus et une installation temporaires."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
import tkinter as tk
from contextlib import ExitStack
from unittest.mock import patch

from cahpp_app.database import Database
from cahpp_app.paths import DATABASE_PATH, ROOT_DIR
from cahpp_app.ui import App, ProductEditDialog


def wait(root, condition, seconds=5):
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        root.update()
        time.sleep(0.01)
    assert condition(), "Action graphique non terminée"


def main(iteration: int):
    database = Database(DATABASE_PATH)
    if iteration == 0:
        database.save_settings(
            {"user_name": "Test", "user_id": "test", "collaboration_enabled": "0"}
        )
        with database.session() as c:
            supplier_id = c.execute(
                "INSERT INTO suppliers(name) VALUES ('FOURNISSEUR.TEST')"
            ).lastrowid
        product_id = database.create_manual_product(
            supplier_id, "REF.01", "ARTICLE.TEST", 10, 0.12, 20
        )
    else:
        with database.connect() as connection:
            supplier_id = connection.execute(
                "SELECT id FROM suppliers WHERE name='FOURNISSEUR.TEST'"
            ).fetchone()[0]
            product_id = connection.execute(
                "SELECT id FROM products WHERE source='LOCAL'"
            ).fetchone()[0]
    errors = []
    with ExitStack() as stack:
        stack.enter_context(patch.object(App, "_start_background_maintenance"))
        stack.enter_context(patch.object(App, "_offer_shared_installer"))
        error_box = stack.enter_context(patch("tkinter.messagebox.showerror"))
        warning_box = stack.enter_context(patch("tkinter.messagebox.showwarning"))
        database = Database(DATABASE_PATH)
        root = tk.Tk()
        root.report_callback_exception = lambda *args: errors.append(args)
        app = App(root, database)
        try:
            app.show_page("suppliers")
            supplier = app.pages["suppliers"]
            supplier.tree.selection_set(str(supplier_id))
            supplier.load_selected()
            if iteration == 0:
                values = {
                    "email": "prenom.nom@example.test",
                    "phone": "03.27.12.34.56",
                    "website": "https://fournisseur.example.test",
                    "contact_name": "M. Test",
                    "minimum_order_ht": "12,50",
                    "franco_ht": "100,00",
                }
                for key, value in values.items():
                    supplier.fields[key].set(value)
                assert supplier.has_unsaved_changes()
                assert supplier.save()
                assert not supplier.has_unsaved_changes()
                dialog = ProductEditDialog(root, database, product_id)
                dialog.vars["supplier_ref"].set("REF.02.A")
                dialog.vars["designation"].set("ARTICLE.V2.TEST")
                dialog.vars["unit_price"].set("0,1250")
                dialog.vars["internal_notes"].set("Note. Avec des points.")
                dialog.save()
                assert dialog.saved

                app.show_page("new_order")
                order = app.pages["new_order"]
                order.supplier_var.set("FOURNISSEUR.TEST")
                order.supplier_changed()
                with patch("tkinter.simpledialog.askfloat", return_value=2):
                    order.add_product_by_id(product_id)
                order.notes_var.set("Note de commande.")
                assert order.has_unsaved_changes()
                with patch("tkinter.messagebox.askyesno", return_value=False):
                    app.close()
                assert root.winfo_exists(), (
                    "La fermeture refusée doit préserver la saisie"
                )
                with patch("tkinter.messagebox.askyesno", return_value=True):
                    assert order.save_draft()
                saved_id = database.list_orders()[0]["id"]
                order.load_order(saved_id)
                assert not order.has_unsaved_changes()
                order.cart_tree.selection_set("0")
                with patch("tkinter.simpledialog.askfloat", return_value=3):
                    order.edit_quantity()
                pdf = ROOT_DIR / "exports" / "commande-test.pdf"
                pdf.parent.mkdir(parents=True, exist_ok=True)
                with (
                    patch("cahpp_app.ui.order.choose_pdf_path", return_value=pdf),
                    patch("cahpp_app.ui.order.open_path"),
                    patch("tkinter.messagebox.askyesno", return_value=True),
                ):
                    assert order.save_and_generate()
                generated, lines = database.get_order(saved_id)
                assert generated["status"] == "Générée"
                assert lines[0]["cartons"] == 3
                app.show_page("orders")
                history = app.pages["orders"]
                history.select_order(saved_id)
                with patch("tkinter.messagebox.askyesno", return_value=True):
                    history.edit_draft()
                reopened, _ = database.get_order(saved_id)
                assert reopened["status"] == "Brouillon"
                assert reopened["pdf_path"] == ""
                assert reopened["order_number"] == generated["order_number"]
                assert pdf.is_file(), (
                    "Le PDF exporté reste sous le contrôle de l'utilisateur"
                )
                assert order.current_order_id == saved_id
                with patch("tkinter.messagebox.askyesno", return_value=True):
                    assert order.save_draft()
            else:
                assert supplier.fields["email"].get() == "prenom.nom@example.test"
                assert supplier.fields["phone"].get() == "03.27.12.34.56"
                assert (
                    supplier.fields["website"].get()
                    == "https://fournisseur.example.test"
                )
                assert supplier.fields["minimum_order_ht"].get() == "12,5"
                dialog = ProductEditDialog(root, database, product_id)
                assert dialog.vars["supplier_ref"].get() == "REF.02.A"
                assert (
                    dialog.vars["internal_notes"].get() == "Note. Avec des points."
                )
                dialog.destroy()
                app.show_page("new_order")
                order = app.pages["new_order"]
                order.load_order(database.list_orders()[0]["id"])
                assert order.cart[0]["cartons"] == 3
                order.product_search_var.set("ARTICLE")
                order.search_products()
                wait(
                    root,
                    lambda: (
                        not order._product_search.pending
                        and order._product_render_after is None
                    ),
                )
                assert order.product_tree.exists(str(product_id))

            # Les workers déposent une réponse ; seul le thread principal exécute Tk.
            received = []
            worker = threading.Thread(
                target=lambda: app.post_ui(
                    lambda: received.append(threading.get_ident())
                )
            )
            worker.start()
            worker.join(timeout=1)
            wait(root, lambda: bool(received))
            assert received == [threading.get_ident()]
            assert not errors, repr(errors)
            error_box.assert_not_called()
            warning_box.assert_not_called()
        finally:
            app.close(force=True)
    print("Fournisseur, article, brouillon, génération, reprise et réouverture : OK")


if __name__ == "__main__":
    if len(sys.argv) == 2:
        main(int(sys.argv[1]))
    else:
        # Un vrai redémarrage crée un nouveau processus et un seul interpréteur Tk.
        # Les deux lancements partagent le même CAHPP_PORTABLE_ROOT temporaire.
        for phase in (0, 1):
            subprocess.run(
                [sys.executable, "-m", "tests.gui_roundtrip", str(phase)], check=True
            )
