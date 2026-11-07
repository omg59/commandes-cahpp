"""Vrai parcours Qt : recherche asynchrone, vérification, panier, PDF et reprise."""

from __future__ import annotations

import sys
import threading
import time
from decimal import Decimal
from functools import partial
from pathlib import Path
from unittest.mock import patch


def wait(app, condition, seconds=8):
    until = time.monotonic() + seconds
    while not condition() and time.monotonic() < until:
        app.processEvents()
        time.sleep(0.01)
    assert condition(), "Action Qt non terminée"


def main():
    from cahpp_app.horizon.bootstrap import configure

    profile, info = configure([])
    from PySide6.QtCore import QCoreApplication, QEvent, QThread, Qt
    from PySide6.QtWidgets import QMessageBox
    from cahpp_app.database import Database
    from cahpp_app.horizon.application import (
        HorizonWindow,
        apply_catalog,
        create_application,
    )
    from cahpp_app.horizon.dialogs import ProductDialog
    from cahpp_app.horizon.services import seed_demo
    from cahpp_app.horizon.theme import apply_theme

    app = create_application()
    errors = []
    sys.excepthook = lambda *args: errors.append(args)
    database = Database(profile / "data/commandes_cahpp.sqlite3")
    seed_demo(database)
    window = HorizonWindow(database, profile, info)
    window.resize(1366, 900)
    window.show()
    with (
        patch("cahpp_app.horizon.application.QMessageBox.warning") as warning,
        patch("cahpp_app.horizon.orders.OrderDispatchDialog.exec", return_value=0),
        patch(
            "cahpp_app.horizon.orders.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ),
    ):
        wait(app, lambda: not window.jobs.tasks)
        assert window.overview.metrics[3].value.text() == "2"
        for key in window.pages:
            window.navigate(key)
            wait(app, lambda: not window.jobs.tasks)
        browser = window.catalog.browser
        window.navigate("catalog")
        browser.query.setText("nitrile")
        browser.search()
        wait(app, lambda: not window.jobs.tasks)
        assert browser.model.rowCount() == 1
        p = browser.rows[0]
        assert p["supplier_ref"] == "DEMO-001"
        with patch(
            "cahpp_app.horizon.orders.QInputDialog.getDouble", return_value=(1.0, True)
        ):
            window.add_product(p)
        assert window.prepare.cart.total_ht == Decimal("4.2100")
        window.prepare.model.setData(
            window.prepare.model.index(0, window.prepare.model.QUANTITY_COLUMN),
            "2",
            Qt.ItemDataRole.EditRole,
        )
        assert window.prepare.cart.total_ht == Decimal("8.4200")
        window.prepare.model.setData(
            window.prepare.model.index(0, window.prepare.model.QUANTITY_COLUMN),
            "NaN",
            Qt.ItemDataRole.EditRole,
        )
        assert window.prepare.cart.total_ht == Decimal("8.4200")
        assert window.prepare.save_draft()
        oid = window.prepare.cart.order_id
        with patch(
            "cahpp_app.horizon.orders.QDesktopServices.openUrl", return_value=True
        ):
            window.prepare.generate_pdf()
        order, _ = database.get_order(oid)
        assert order["status"] == "Générée" and Path(order["pdf_path"]).is_file()
        pdf = Path(order["pdf_path"])
        assert profile in pdf.parents
        window.orders.selected_id = oid
        with patch(
            "cahpp_app.horizon.orders.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            window.orders.resume_order()
        assert (
            window.prepare.cart.order_id == oid
            and database.get_order(oid)[0]["status"] == "Brouillon"
        )
        window.prepare.model.setData(
            window.prepare.model.index(0, window.prepare.model.QUANTITY_COLUMN),
            "3",
            Qt.ItemDataRole.EditRole,
        )
        assert window.prepare.save_draft()
        with database.connect() as c:
            pid = c.execute(
                "SELECT id FROM products WHERE supplier_ref='DEMO-007'"
            ).fetchone()[0]
        dialog = ProductDialog(database, pid, window)
        dialog.fields["conditionnement"].setText("40")
        dialog.save()
        assert not dialog.saved and dialog.error.isVisibleTo(dialog)
        dialog.confirm.setChecked(True)
        dialog.save()
        assert dialog.saved
        assert not database.get_product(pid)["catalog_review_required"]
        assert database.get_product(pid)["conditionnement"] == 40
        apply_theme(app, True)
        window.overview.chart.repaint()
        app.processEvents()
        apply_theme(app, False)
        result_threads = []
        window.jobs.submit(
            "thread-check",
            lambda **kw: threading.get_ident(),
            lambda result, error: result_threads.append(
                (result, QThread.currentThread() == app.thread())
            ),
        )
        wait(app, lambda: bool(result_threads))
        assert result_threads[0][0] != threading.get_ident() and result_threads[0][1]
        outcomes = []

        def slow(value, *, cancel, progress):
            time.sleep(0.08)
            return value

        window.jobs.submit(
            "latest",
            partial(slow, "old"),
            lambda result, error: outcomes.append(result),
        )
        window.jobs.submit(
            "latest",
            partial(slow, "new"),
            lambda result, error: outcomes.append(result),
        )
        wait(app, lambda: not window.jobs.tasks)
        assert outcomes == ["new"], outcomes
        # Le moteur d'import est aussi utilisable depuis un worker Qt.
        from tests.test_monthly_catalog import create_monthly, monthly_row
        from tests.test_workflow import create_catalog
        from cahpp_app.catalog_importer import CatalogImporter, ImportOptions

        base = profile / "test-base.xlsx"
        create_catalog(
            base,
            [
                {
                    "Catalogue": "DM",
                    "IDFournisseur": 999,
                    "NomFournisseur": "Fournisseur test",
                    "CodeCahpp": "QT-001",
                    "RéférenceArticle": "QT-001",
                    "DésignationArticle": "ARTICLE QT TEST",
                    "PrixUnitaireCahpp": 1,
                    "Conditionnement": 10,
                    "Qml": 10,
                    "TVA": 20,
                }
            ],
        )
        importer = CatalogImporter(database)
        importer.import_file(base)
        delta = profile / "test-delta.xlsx"
        row = monthly_row("QT-001")
        row["NOM_FOURNISSEUR"] = "Fournisseur test"
        row["CODE_FOURNISSEUR"] = 999
        create_monthly(delta, [row])
        preview = importer.inspect_file(delta)
        imported = []
        window.jobs.submit(
            "test-import",
            partial(
                apply_catalog,
                database,
                delta,
                preview,
                ImportOptions(confirm_baseline=True),
            ),
            lambda result, error: imported.append((result, error)),
        )
        wait(app, lambda: bool(imported))
        assert imported[0][1] is None, imported[0][1]
        assert list((profile / "sauvegardes").glob("horizon-avant-import-*.zip"))
        warning.assert_not_called()
        assert not errors, repr(errors)
        # Fermer après une recherche en cours ne livre aucun résultat au widget détruit.
        window.catalog.browser.query.setText("ARTICLE")
        window.catalog.browser.search()
        window.prepare.cart.dirty = False
        window.close()
        wait(app, lambda: not window.isVisible())
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        reopened = HorizonWindow(
            Database(profile / "data/commandes_cahpp.sqlite3"), profile, info
        )
        reopened.show()
        reopened.prepare.load_order(oid)
        assert reopened.prepare.cart.lines[0].cartons == Decimal(3)
        assert reopened.prepare.cart.order_id == oid
        reopened.close()
        wait(app, lambda: not reopened.isVisible())
        assert not errors, repr(errors)
    print("HORIZON_QT_OK")


if __name__ == "__main__":
    main()
