"""La génération PDF reste une seule action avant toute synchro d'arrière-plan."""

from unittest.mock import patch
from tests.gui_horizon import wait


def main():
    from cahpp_app.horizon.bootstrap import configure

    profile, info = configure([])
    from cahpp_app.database import Database
    from cahpp_app.horizon.application import HorizonWindow, create_application
    from cahpp_app.horizon.dispatch import OrderDispatchDialog
    from PySide6.QtWidgets import QMessageBox

    app = create_application()
    db = Database(profile / "data/commandes_cahpp.sqlite3")
    with db.session() as c:
        sid = c.execute(
            "INSERT INTO suppliers(name,email) VALUES ('Fournisseur RC1','test@example.invalid')"
        ).lastrowid
    pid = db.create_manual_product(sid, "RC1", "Article", 10, 1, 20)
    db.save_settings(
        {
            "collaboration_enabled": "1",
            "shared_workspace_path": str(profile / "partage"),
        }
    )
    window = HorizonWindow(db, profile, info)
    window.show()
    wait(app, lambda: not window.jobs.tasks)
    window.add_product(db.get_product(pid), quantity=2)
    wait(app, lambda: not window.jobs.tasks)
    from cahpp_app.horizon.dialogs import ProductDialog
    from cahpp_app.collaboration import CollaborationManager
    remote = CollaborationManager(db, "poste-rc1-distinct", "Autre poste", profile / "partage")
    remote.initialize_workspace()
    with remote.acquire_lock("produit", db.get_product(pid)["code_cahpp"]):
        dialog = ProductDialog(db, pid, window, operations=window.operations)
        dialog.fields["designation"].setText("Modification refusée")
        dialog.save()
        assert not dialog.saved
        assert "ressource" in dialog.error.text()
        assert db.get_product(pid)["designation"] == "Article"
    dialog = ProductDialog(db, pid, window, operations=window.operations)
    db.update_product_team_details(pid, "Note plus récente", "")
    dialog.save()
    assert not dialog.saved and "changé" in dialog.error.text()
    events = []
    original_changed = window.data_changed

    def changed():
        order, _ = db.get_order(window.prepare.cart.order_id)
        # No data_changed (and thus sync worker) between save and PDF creation.
        assert order["pdf_path"], "Synchronisation déclenchée avant la fin du PDF"
        events.append("document prêt")
        original_changed()

    with (
        patch.object(window, "data_changed", side_effect=changed),
        patch.object(OrderDispatchDialog, "exec", return_value=0),
        patch.object(QMessageBox, "warning") as errors,
    ):
        window.prepare.generate_pdf()
        wait(app, lambda: not window.jobs.tasks)
        errors.assert_not_called()
    assert events
    order, _ = db.get_order(window.prepare.cart.order_id)
    assert order["status"] == "Générée"
    from pathlib import Path
    assert Path(order["pdf_path"]).name == f"BC-{order['order_date']}_Fournisseur RC1.pdf"
    window.close()
    wait(app, lambda: not window.isVisible())


if __name__ == "__main__":
    main()
