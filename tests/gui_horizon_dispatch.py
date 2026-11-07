"""Parcours réel PDF → messagerie → confirmation, sans quitter la préparation."""

import sys
from pathlib import Path
from unittest.mock import patch

from tests.gui_horizon import wait


def main():
    from cahpp_app.horizon.bootstrap import configure

    profile, info = configure([])
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox
    from cahpp_app.database import Database
    from cahpp_app.horizon.application import HorizonWindow, create_application
    from cahpp_app.horizon.dispatch import OrderDispatchDialog
    from cahpp_app.horizon.services import seed_demo

    app = create_application()
    db = Database(profile / "data/commandes_cahpp.sqlite3")
    seed_demo(db)
    window = HorizonWindow(db, profile, info)
    window.resize(1366, 900)
    window.show()
    with (
        patch(
            "PySide6.QtWidgets.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ),
        patch("PySide6.QtWidgets.QMessageBox.warning") as warnings,
        patch("PySide6.QtGui.QDesktopServices.openUrl", return_value=True) as external,
    ):
        wait(app, lambda: not window.jobs.tasks)
        with db.connect() as c:
            pid = c.execute(
                "SELECT id FROM products WHERE supplier_ref='DEMO-001'"
            ).fetchone()[0]
        product = db.get_product(pid)
        sid = product["supplier_id"]
        with db.session() as c:
            c.execute(
                "UPDATE suppliers SET email='commandes@example.org' WHERE id=?", (sid,)
            )
        window.add_product(product, quantity=2)
        wait(app, lambda: not window.jobs.tasks)
        assert window.prepare.save_draft()
        oid = window.prepare.cart.order_id
        attachment = profile / "conditions.txt"
        attachment.write_text("Document fictif à joindre", encoding="utf-8")
        db.add_order_attachment(oid, "Autre", attachment.name, str(attachment), True)

        # Ni l'annulation du choix de fichier ni une erreur PDF ne proposent
        # l'envoi d'un bon qui n'a pas été produit.
        with (
            patch(
                "PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=("", "")
            ),
            patch.object(OrderDispatchDialog, "exec") as popup,
        ):
            window.prepare.generate_pdf(choose=True)
            popup.assert_not_called()
        assert db.get_order(oid)[0]["status"] == "Brouillon"
        with (
            patch(
                "cahpp_app.pdf_export.generate_order_pdf",
                side_effect=OSError("Écriture refusée"),
            ),
            patch.object(OrderDispatchDialog, "exec") as popup,
        ):
            window.prepare.generate_pdf()
            popup.assert_not_called()
        warnings.assert_called_once()
        warnings.reset_mock()

        # Exercer la vraie fenêtre modale ouverte par la génération du PDF.
        failures = []

        def later():
            dialog = QApplication.activeModalWidget()
            try:
                assert isinstance(dialog, OrderDispatchDialog)
                assert window.stack.currentWidget() is window.containers["prepare"]
                assert dialog.order_id == oid
                assert "commandes@example.org" in dialog.recipient.text()
                assert dialog.pdf_path.is_file()
                assert not dialog.sent_button.isEnabled()
                assert dialog.compose_button.text() == "Envoyer l'e-mail au fournisseur"
                if len(sys.argv) > 1:
                    dialog.grab().save(sys.argv[1])
                dialog.later_button.click()
            except BaseException as exc:
                failures.append(exc)
                if dialog:
                    dialog.reject()

        QTimer.singleShot(100, later)
        window.prepare.generate_pdf()
        assert not failures, failures
        external.assert_not_called()
        order, _ = db.get_order(oid)
        assert order["status"] == "Générée" and not order["sent_at"]
        assert window.prepare.send_button.isVisible()

        # Une messagerie indisponible ne doit pas annoncer un message ouvert.
        dialog = OrderDispatchDialog(window, oid)
        with patch("PySide6.QtGui.QDesktopServices.openUrl", return_value=False):
            dialog.compose()
        warnings.assert_called_once()
        warnings.reset_mock()
        assert not dialog.sent_button.isEnabled()
        assert dialog.compose_button.text() == "Envoyer l'e-mail au fournisseur"
        assert db.get_order(oid)[0]["status"] == "Générée"
        dialog.reject()

        # Reprendre l'envoi en un clic depuis la même page. Le PDF ET les
        # documents cochés sont préparés, sans jamais enregistrer un envoi réel.
        prepared = []

        def compose_later():
            dialog = QApplication.activeModalWidget()
            try:
                assert isinstance(dialog, OrderDispatchDialog)
                dialog.compose_button.click()
                assert (
                    dialog.compose_button.text()
                    == "Envoyer à nouveau l'e-mail au fournisseur"
                )
                assert dialog.sent_button.isEnabled()
                assert dialog.directory.is_dir()
                assert (dialog.directory / attachment.name).is_file()
                assert any(dialog.directory.glob("*.pdf"))
                assert db.get_order(oid)[0]["status"] == "E-mail préparé"
                assert not db.get_order(oid)[0]["sent_at"]
                prepared.append(dialog.directory)
                dialog.later_button.click()
            except BaseException as exc:
                failures.append(exc)
                if dialog:
                    dialog.reject()

        QTimer.singleShot(100, compose_later)
        window.prepare.send_button.click()
        assert not failures, failures
        assert len(prepared) == 1
        urls = [call.args[0] for call in external.call_args_list]
        assert any(url.isLocalFile() for url in urls)
        assert any("commandes%40example.org" in url.toString() for url in urls)
        assert not db.get_order(oid)[0]["sent_at"]
        assert window.stack.currentWidget() is window.containers["prepare"]

        # L'absence d'e-mail indique le problème et mène à la bonne fiche,
        # maintenant située dans Paramètres → Fournisseurs.
        with db.session() as c:
            c.execute("UPDATE suppliers SET email='' WHERE id=?", (sid,))
        missing = OrderDispatchDialog(window, oid)
        assert not missing.compose_button.isEnabled()
        window.suppliers.query.setText("Carevia")
        missing.edit_supplier()
        assert window.stack.currentWidget() is window.containers["settings"]
        assert window.preferences.tabs.currentWidget() is window.suppliers
        assert window.suppliers.current_id == sid
        assert "suppliers" not in window.nav_buttons
        assert "suppliers" not in window.pages
        if len(sys.argv) > 1:
            app.processEvents()
            window.grab().save(
                str(Path(sys.argv[1]).with_name("horizon-a5-suppliers.png"))
            )
        window.suppliers.fields.widgets["email"].setText("commandes@example.org")
        assert window.suppliers.save()
        window.navigate("prepare")
        wait(app, lambda: not window.jobs.tasks)

        # La confirmation explicite termine le parcours et libère le panier.
        dialog = OrderDispatchDialog(window, oid)
        dialog.show()
        # Le message est déjà préparé : inutile de le rouvrir pour confirmer.
        assert dialog.sent_button.isEnabled()
        assert (
            dialog.compose_button.text() == "Envoyer à nouveau l'e-mail au fournisseur"
        )
        assert not db.get_order(oid)[0]["sent_at"]
        folder = prepared[0]
        dialog.sent_button.click()
        assert db.get_order(oid)[0]["status"] == "Envoyée"
        assert db.get_order(oid)[0]["sent_at"]
        assert not folder.exists()
        assert not window.prepare.cart.lines
        assert window.stack.currentWidget() is window.containers["prepare"]
        assert not dialog.isVisible()
        assert not window.prepare.send_button.isVisible()
        warnings.assert_not_called()
        wait(app, lambda: not window.jobs.tasks)
        window.close()
        wait(app, lambda: not window.isVisible())
    print("HORIZON_DISPATCH_OK")


if __name__ == "__main__":
    main()
