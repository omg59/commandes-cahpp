"""Demande native de quantité, cumul et annulation sans perdre la commande."""

import sys
from decimal import Decimal
from unittest.mock import patch

from tests.gui_horizon import wait


def main():
    from cahpp_app.horizon.bootstrap import configure

    profile, info = configure([])
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QSpinBox, QInputDialog
    from cahpp_app.database import Database
    from cahpp_app.horizon.application import HorizonWindow, create_application
    from cahpp_app.horizon.services import seed_demo

    app = create_application()
    db = Database(profile / "data/commandes_cahpp.sqlite3")
    seed_demo(db)
    with db.session() as connection:
        pid = connection.execute(
            "SELECT id FROM products WHERE supplier_ref='DEMO-001'"
        ).fetchone()[0]
        other_id = connection.execute(
            "SELECT id FROM products WHERE supplier_ref='DEMO-003'"
        ).fetchone()[0]
        connection.execute("UPDATE products SET usual_cartons=1.25 WHERE id=?", (pid,))
    product = db.get_product(pid)
    window = HorizonWindow(db, profile, info)
    window.resize(1366, 900)
    window.show()
    with patch.object(window, "report_error") as errors:
        wait(app, lambda: not window.jobs.tasks)
        window.add_product(product, quantity=1)
        window.navigate("catalog")
        window.catalog.browser.query.setText("nitrile")
        window.catalog.browser.search()
        wait(app, lambda: not window.jobs.tasks)
        window.catalog.browser.table.selectRow(0)
        failures = []

        def confirm():
            dialog = QApplication.activeModalWidget()
            try:
                assert isinstance(dialog, QInputDialog)
                assert dialog.windowTitle() == "Quantité à ajouter"
                assert dialog.width() >= 420, (dialog.width(), dialog.minimumWidth())
                assert dialog.inputMode() == QInputDialog.InputMode.IntInput
                spin = dialog.findChild(QSpinBox)
                assert spin.value() == 1, spin.value()
                assert spin.minimum() == 1, spin.minimum()
                spin.setValue(2)
                assert spin.text() == "2", spin.text()
                if len(sys.argv) > 1:
                    dialog.grab().save(sys.argv[1])
                dialog.accept()
            except BaseException as exc:
                failures.append(exc)
                if dialog:
                    dialog.reject()

        QTimer.singleShot(100, confirm)
        window.catalog.add.click()
        assert not failures, failures
        assert window.current_page() is window.prepare
        assert window.prepare.cart.lines[0].cartons == Decimal("3")
        cart = window.prepare.cart

        def cancel():
            dialog = QApplication.activeModalWidget()
            try:
                assert isinstance(dialog, QInputDialog)
                dialog.reject()
            except BaseException as exc:
                failures.append(exc)
                if dialog:
                    dialog.reject()

        with patch.object(window, "allow_discard_or_save") as discard:
            QTimer.singleShot(100, cancel)
            window.add_product(db.get_product(other_id))
            discard.assert_not_called()
        assert not failures, failures
        assert window.prepare.cart is cart
        assert len(cart.lines) == 1 and cart.lines[0].cartons == Decimal("3")
        assert cart.supplier_id == product["supplier_id"]
        window.prepare.reset()
        window.navigate("statistics")
        wait(app, lambda: not window.jobs.tasks)
        window.resize(900, 600)
        app.processEvents()
        selector = window.statistics.supplier
        assert selector.currentText() == "Tous les fournisseurs"
        editor = selector.lineEdit()
        expected = editor.fontMetrics().horizontalAdvance(selector.currentText()) + 40
        assert editor.width() >= expected, (selector.width(), editor.width(), expected)
        errors.assert_not_called()
        window.close()
        wait(app, lambda: not window.isVisible())
    print("HORIZON_QUANTITY_OK")


if __name__ == "__main__":
    main()
