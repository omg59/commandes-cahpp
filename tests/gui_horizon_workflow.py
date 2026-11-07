"""Parcours Qt complet : réglages, fournisseur, commande, BL, PDF et diagnostic."""

import sys
from pathlib import Path
from unittest.mock import patch

from tests.gui_horizon import wait


def main():
    from cahpp_app.horizon.bootstrap import configure

    profile, info = configure([])
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox, QPushButton
    from cahpp_app.database import Database
    from cahpp_app.horizon.application import HorizonWindow, create_application
    from cahpp_app.horizon.services import seed_demo
    from cahpp_app.horizon.services import Cart
    from cahpp_app.horizon.settings import DiagnosticDialog
    from cahpp_app.horizon.tracking import OrderWorkspaceDialog, ReceiptDialog
    from cahpp_app.app_logging import configure_logging
    from openpyxl import load_workbook

    app = create_application()
    configure_logging()
    errors = []
    sys.excepthook = lambda *args: errors.append(args)
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
        patch("PySide6.QtWidgets.QMessageBox.information"),
        patch("PySide6.QtWidgets.QMessageBox.warning") as warnings,
        patch("PySide6.QtGui.QDesktopServices.openUrl", return_value=True),
    ):
        for name in window.pages:
            window.navigate(name)
            wait(app, lambda: not window.jobs.tasks)
        window.preferences.widget("establishment_name").setText("Établissement d'essai")
        window.preferences.widget("email").setText("service.test@example.org")
        assert window.preferences.has_unsaved_changes()
        assert window.preferences.save()
        assert not window.preferences.has_unsaved_changes()
        assert db.get_settings()["email"] == "service.test@example.org"
        window.navigate("suppliers")
        wait(app, lambda: not window.jobs.tasks)
        sid = window.suppliers.current_id
        assert sid
        window.suppliers.fields.widgets["email"].setText(
            "commande.fournisseur@example.org"
        )
        window.suppliers.fields.widgets["contact_name"].setText(
            "Mme Test — 03.27.00.00.00"
        )
        window.suppliers.fields.widgets["franco_ht"].setText("12,50")
        save = next(
            b
            for b in window.suppliers.findChildren(QPushButton)
            if b.text() == "Enregistrer la fiche"
        )
        save.click()
        assert db.get_supplier(sid)["email"] == "commande.fournisseur@example.org"
        assert db.get_supplier(sid)["franco_ht"] == 12.5
        assert not window.suppliers.has_unsaved_changes()
        with db.connect() as c:
            pid = c.execute(
                "SELECT id FROM products WHERE supplier_id=? AND catalog_review_token='' ORDER BY id LIMIT 1",
                (sid,),
            ).fetchone()[0]
        p = db.get_product(pid)
        window.add_product(p, quantity=3)
        wait(app, lambda: not window.jobs.tasks)
        window.prepare.requester.setText("Service d'essai")
        assert window.prepare.save_draft()
        oid = window.prepare.cart.order_id
        # Un total exactement égal à un franco décimal ne doit pas déclencher
        # un faux avertissement dû à la représentation binaire d'un float.
        original_cart = window.prepare.cart
        threshold_cart = Cart()
        threshold_cart.add(p, price="0.10", packaging=1, quantity=1)
        threshold_cart.order_id = oid
        with db.session() as c:
            c.execute("UPDATE suppliers SET franco_ht=0.1 WHERE id=?", (sid,))
        window.prepare.cart = threshold_cart
        window.prepare.update_totals()
        assert window.prepare.franco.text() == "Franco atteint"
        with patch("PySide6.QtWidgets.QMessageBox.question") as threshold_warning:
            assert window.prepare.confirm_warnings()
            threshold_warning.assert_not_called()
        window.prepare.cart = original_cart
        with db.session() as c:
            c.execute("UPDATE suppliers SET franco_ht=12.5 WHERE id=?", (sid,))
        window.prepare.update_totals()
        window.prepare.generate_pdf()
        order, lines = db.get_order(oid)
        assert order["requester_service"] == "Service d'essai"
        assert Path(order["pdf_path"]).is_file()
        window.orders.selected_id = oid
        window.orders.mark_sent()
        wait(app, lambda: not window.jobs.tasks)
        assert db.get_order(oid)[0]["sent_at"]
        workspace = OrderWorkspaceDialog(window, oid)
        workspace.expected.setText("2030-12-25")
        workspace.confirm()
        workspace.comment.setPlainText("Vérifier la deuxième livraison")
        workspace.add_comment()
        assert (
            db.list_order_comments(oid)[0]["body"] == "Vérifier la deuxième livraison"
        )
        receipt = ReceiptDialog(window, oid)
        qty_index = receipt.model.index(0, 3)
        assert receipt.model.setData(qty_index, "1", Qt.ItemDataRole.EditRole)
        receipt.fields.widgets["reference"].setText("BL-QT-1")
        receipt.save()
        assert db.get_order(oid)[0]["delivery_status"] == "Partiellement livrée"
        workspace.refresh()
        assert workspace.receipts_model.rowCount() == 1
        fixture = profile / "bl-test.txt"
        fixture.write_text("Document de livraison fictif", encoding="utf-8")
        with patch(
            "PySide6.QtWidgets.QFileDialog.getOpenFileNames",
            return_value=([str(fixture)], ""),
        ):
            workspace.attach()
        workspace.documents_table.selectRow(0)
        assert workspace.documents_model.rowCount() == 1
        workspace.toggle_attachment()
        assert db.list_order_attachments(oid)[0]["include_in_email"]
        receipt2 = ReceiptDialog(window, oid)
        receipt2.fill(True)
        receipt2.save()
        workspace.invoice()
        assert db.get_order(oid)[0]["delivery_status"] == "Livrée"
        assert db.get_order(oid)[0]["invoiced_at"]
        window.orders.prepare_email()
        assert list((profile / "envois").rglob("bl-test.txt"))
        window.orders.duplicate()
        duplicate = window.prepare.cart.order_id
        assert duplicate != oid and db.get_order(duplicate)[0]["status"] == "Brouillon"
        assert len(db.get_order(duplicate)[1]) == len(lines)
        window.orders.selected_id = oid
        with patch(
            "PySide6.QtWidgets.QInputDialog.getText",
            return_value=("Livraisons terminées", True),
        ):
            window.orders.save_filter()
        assert db.list_saved_order_filters()[0]["name"] == "Livraisons terminées"
        window.navigate("statistics")
        wait(app, lambda: not window.jobs.tasks)
        destination = profile / "stats-test.xlsx"
        with patch(
            "PySide6.QtWidgets.QFileDialog.getSaveFileName",
            return_value=(str(destination), ""),
        ):
            window.statistics.export_excel()
        wait(app, lambda: not window.jobs.tasks)
        workbook = load_workbook(destination, read_only=True)
        assert "Produits" in workbook.sheetnames or "Articles" in workbook.sheetnames
        workbook.close()
        backup = profile / "backup-test.zip"
        with patch(
            "PySide6.QtWidgets.QFileDialog.getSaveFileName",
            return_value=(str(backup), ""),
        ):
            window.preferences.backup()
        wait(app, lambda: not window.jobs.tasks)
        assert backup.is_file()
        # Le diagnostic ne répare rien avant l'action explicite.
        with db.session() as c:
            c.execute("DELETE FROM product_search")
        diagnostic = DiagnosticDialog(window)
        wait(app, lambda: not window.jobs.tasks)
        assert "À RÉPARER" in diagnostic.report
        diagnostic.repair()
        wait(app, lambda: not window.jobs.tasks)
        assert "Index de recherche : OK" in diagnostic.report
        diagnostic.copy()
        assert app.clipboard().text() == diagnostic.report
        report = profile / "diagnostic-test.txt"
        with patch(
            "PySide6.QtWidgets.QFileDialog.getSaveFileName",
            return_value=(str(report), ""),
        ):
            diagnostic.export()
        assert "PySide6" in report.read_text(encoding="utf-8")
        assert "Vérifier la deuxième livraison" not in report.read_text(
            encoding="utf-8"
        )
        diagnostic.reject()
        workspace.reject()
        window.prepare.reset()
        if len(sys.argv) > 1:
            window.navigate("orders")
            wait(app, lambda: not window.jobs.tasks)
            window.grab().save(sys.argv[1])
        warnings.assert_not_called()
        assert not errors, repr(errors)
        window.close()
        wait(app, lambda: not window.isVisible())
    print("HORIZON_COMPLETE_WORKFLOW_OK")


if __name__ == "__main__":
    main()
