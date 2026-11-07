"""Capture réelle de l'interface, avec des données fictives dans un profil temporaire."""

import argparse
import os
import tempfile
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="horizon-capture-") as folder:
        os.environ["CAHPP_HORIZON_ROOT"] = folder
        from cahpp_app.horizon.bootstrap import configure

        profile, info = configure(["--profile", str(Path(folder) / "profil")])
        from PySide6.QtCore import Qt
        from cahpp_app.database import Database
        from cahpp_app.horizon.application import HorizonWindow, create_application
        from cahpp_app.horizon.services import seed_demo

        app = create_application()
        database = Database(profile / "data/commandes_cahpp.sqlite3")
        seed_demo(database)
        with database.session() as connection:
            connection.execute(
                "UPDATE suppliers SET name=replace(name,' — démonstration','')"
            )
            connection.execute(
                "UPDATE products SET supplier_name=(SELECT name FROM suppliers WHERE id=products.supplier_id), supplier_ref=replace(supplier_ref,'DEMO-','REF-')"
            )
        database.save_settings(
            {"establishment_name": "Établissement exemple", "user_name": "Damien Macq"}
        )
        window = HorizonWindow(database, profile, info)
        window.resize(1440, 960)
        window.show()
        with database.connect() as connection:
            products = [
                database.get_product(r[0])
                for r in connection.execute(
                    "SELECT id FROM products WHERE supplier_ref IN ('REF-001','REF-002') ORDER BY id"
                )
            ]
        for product, quantity in zip(products, (2, 3)):
            window.prepare.add(product, quantity=quantity)
        window.prepare.requester.setText("Service de soins")
        window.prepare.order_date.setText("08/11/2026")
        window.navigate("prepare")
        until = time.monotonic() + 10
        while window.jobs.tasks and time.monotonic() < until:
            app.processEvents()
            time.sleep(0.01)
        assert not window.jobs.tasks
        window.prepare.browser.table.clearSelection()
        window.setFocus(Qt.FocusReason.OtherFocusReason)
        app.processEvents()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        assert window.grab().save(str(args.output))
        window.prepare.cart.dirty = False
        window.close()
        until = time.monotonic() + 5
        while window.isVisible() and time.monotonic() < until:
            app.processEvents()
            time.sleep(0.01)
        assert not window.isVisible()


if __name__ == "__main__":
    main()
