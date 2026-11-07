"""Parcours Qt complet : réglages, fournisseur, commande, BL, PDF et diagnostic."""

import sys
from pathlib import Path
from unittest.mock import patch

from tests.gui_horizon import wait


def main():
    from cahpp_app.horizon.bootstrap import configure

    profile, info = configure([])
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox, QPushButton, QFrame
    from PySide6.QtTest import QTest
    from cahpp_app.database import Database
    from cahpp_app.horizon.application import HorizonWindow, create_application
    from cahpp_app.horizon.services import seed_demo
    from cahpp_app.horizon.services import Cart
    from cahpp_app.horizon.settings import DiagnosticDialog
    from cahpp_app.horizon.models import RowsModel, date_column
    from cahpp_app.horizon.dispatch import OrderDispatchDialog
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
        patch.object(OrderDispatchDialog, "exec", return_value=0),
    ):
        topbar = window.findChild(QFrame, "topbar")
        assert not topbar.findChildren(QPushButton)
        assert window.preferences.isAncestorOf(window.preferences.copy_database_button)
        assert window.theme_switch.isChecked() is False
        window.theme_switch.click()
        assert app.property("horizonDark") is True
        assert window.settings.value("dark", type=bool) is True
        QTest.keyClick(window.theme_switch, Qt.Key.Key_Space)
        assert app.property("horizonDark") is False
        # La saisie filtre aussi au milieu du nom. Tant que le fournisseur
        # n'est pas choisi, l'ancien identifiant n'est jamais réutilisé.
        window.navigate("prepare")
        picker = window.prepare.suppliers
        picker.lineEdit().clear()
        QTest.keyClicks(picker.lineEdit(), "revia")
        assert picker.currentData() is None
        completer = picker.completer()
        completer.setCompletionPrefix("revia")
        assert completer.completionCount() == 1
        popup = completer.popup()
        popup.setCurrentIndex(completer.completionModel().index(0, 0))
        QTest.keyClick(popup, Qt.Key.Key_Return)
        wait(app, lambda: picker.currentData() is not None and not window.jobs.tasks)
        assert "Carevia" in picker.currentText()
        supplier_id = picker.currentData()
        picker.setEditText(picker.currentText().upper())
        assert picker.currentData() is None
        picker.accept_exact()
        assert picker.currentData() == supplier_id
        command_columns = [c[0] for c in window.prepare.browser.model.columns]
        assert command_columns[:2] == ["Référence", "Désignation"]
        assert [c[0] for c in window.prepare.model.columns][:2] == [
            "Référence",
            "Désignation",
        ]
        for name in window.pages:
            window.navigate(name)
            wait(app, lambda: not window.jobs.tasks)
        window.preferences.widget("establishment_name").setText("Établissement d'essai")
        window.preferences.widget("email").setText("service.test@example.org")
        assert window.preferences.has_unsaved_changes()
        assert window.preferences.save()
        assert not window.preferences.has_unsaved_changes()
        assert db.get_settings()["email"] == "service.test@example.org"
        assert "suppliers" not in window.nav_buttons
        window.navigate("settings")
        tabs = window.preferences.tabs
        supplier_tab = tabs.indexOf(window.suppliers)
        assert tabs.tabText(supplier_tab) == "Fournisseurs"
        QTest.mouseClick(
            tabs.tabBar(),
            Qt.MouseButton.LeftButton,
            pos=tabs.tabBar().tabRect(supplier_tab).center(),
        )
        assert tabs.currentWidget() is window.suppliers
        assert not window.preferences.save_button.isVisible()
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
        assert window.prepare.browser.model.columns[1][1](p) == p["designation"]
        assert (
            window.prepare.model.setData(
                window.prepare.model.index(0, 0),
                "autre référence",
                Qt.ItemDataRole.EditRole,
            )
            is False
        )
        assert window.prepare.model.setData(
            window.prepare.model.index(0, window.prepare.model.QUANTITY_COLUMN),
            "4",
            Qt.ItemDataRole.EditRole,
        )
        assert window.prepare.cart.lines[0].cartons == 4
        window.prepare.model.setData(
            window.prepare.model.index(0, window.prepare.model.QUANTITY_COLUMN),
            "3",
            Qt.ItemDataRole.EditRole,
        )
        if len(sys.argv) > 1:
            app.processEvents()
            window.grab().save(
                str(Path(sys.argv[1]).with_name("horizon-a3-commande.png"))
            )
            window.theme_switch.click()
            app.processEvents()
            window.grab().save(
                str(Path(sys.argv[1]).with_name("horizon-a3-sombre.png"))
            )
            window.theme_switch.click()
        window.prepare.requester.setText("Service d'essai")
        window.prepare.order_date.setText("05/02/2026")
        assert window.prepare.save_draft()
        oid = window.prepare.cart.order_id
        assert db.get_order(oid)[0]["order_date"] == "2026-02-05"
        assert window.prepare.order_date.text() == "05/02/2026"
        # Le tri utilise les dates réelles, pas l'ordre alphabétique des jours.
        dated = RowsModel([date_column("Date", "date")])
        dated.replace(
            [{"date": "2027-01-01"}, {"date": "2026-12-31"}, {"date": "2026-01-02"}]
        )
        dated.sort(0)
        assert [r["date"] for r in dated.rows] == [
            "2026-01-02",
            "2026-12-31",
            "2027-01-01",
        ]
        assert dated.data(dated.index(0, 0)) == "02/01/2026"
        dated.sort(0, Qt.SortOrder.DescendingOrder)
        assert dated.data(dated.index(0, 0)) == "01/01/2027"
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
        assert Path(order["pdf_path"]).name.startswith("05-02-2026")
        window.orders.selected_id = oid
        window.orders.mark_sent()
        wait(app, lambda: not window.jobs.tasks)
        assert db.get_order(oid)[0]["sent_at"]
        window.open_order(oid)
        wait(app, lambda: not window.jobs.tasks)
        selected_row = next(
            i for i, r in enumerate(window.orders.model.rows) if r["id"] == oid
        )
        assert (
            window.orders.model.data(window.orders.model.index(selected_row, 1))
            == "05/02/2026"
        )
        assert "Préparée le 05/02/2026" in window.orders.details.text()
        workspace = OrderWorkspaceDialog(window, oid)
        workspace.expected.setText("25/12/2030")
        workspace.confirm()
        assert db.get_order(oid)[0]["expected_delivery_date"] == "2030-12-25"
        assert workspace.expected.text() == "25/12/2030"
        workspace.comment.setPlainText("Vérifier la deuxième livraison")
        workspace.add_comment()
        assert (
            db.list_order_comments(oid)[0]["body"] == "Vérifier la deuxième livraison"
        )
        receipt = ReceiptDialog(window, oid)
        receipt.fields.widgets["date"].setText("09/02/2026")
        qty_index = receipt.model.index(0, 3)
        assert receipt.model.setData(qty_index, "1", Qt.ItemDataRole.EditRole)
        receipt.fields.widgets["reference"].setText("BL-QT-1")
        receipt.save()
        assert db.get_order(oid)[0]["delivery_status"] == "Partiellement livrée"
        workspace.refresh()
        assert workspace.receipts_model.rowCount() == 1
        assert (
            workspace.receipts_model.data(workspace.receipts_model.index(0, 1))
            == "09/02/2026"
        )
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
        with patch.object(OrderDispatchDialog, "exec", lambda dialog: dialog.compose()):
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
        window.statistics.from_date.setText("01/02/2026")
        window.statistics.to_date.setText("28/02/2026")
        window.statistics.refresh()
        wait(app, lambda: not window.jobs.tasks)
        assert window.statistics.dataset["date_from"].isoformat() == "2026-02-01"
        assert window.statistics.dataset["totals"]["orders"] == 1
        destination = profile / "stats-test.xlsx"
        with patch(
            "PySide6.QtWidgets.QFileDialog.getSaveFileName",
            return_value=(str(destination), ""),
        ):
            window.statistics.export_excel()
        wait(app, lambda: not window.jobs.tasks)
        workbook = load_workbook(destination, read_only=True)
        assert workbook["Synthèse"]["B2"].number_format == "dd/mm/yyyy"
        assert workbook["Synthèse"]["B2"].is_date
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
