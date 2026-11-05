"""Réparation par le vrai bouton Tk, succès, échec et fermeture pendant le worker."""

from __future__ import annotations

import sqlite3
import threading
import tkinter as tk
from unittest.mock import patch

from cahpp_app.database import Database
from cahpp_app.paths import DATABASE_PATH
from cahpp_app.ui import App, DiagnosticDialog
from tests.gui_roundtrip import wait


def main():
    database = Database(DATABASE_PATH)
    database.save_settings(
        {"user_name": "Test", "user_id": "test", "collaboration_enabled": "0"}
    )
    with database.session() as connection:
        supplier = connection.execute(
            "INSERT INTO suppliers(name) VALUES ('TEST')"
        ).lastrowid
    product = database.create_manual_product(
        supplier, "TEST001", "GANT NITRILE", 1, 1, 20
    )
    root = tk.Tk()
    errors = []
    root.report_callback_exception = lambda *args: errors.append(args)
    with (
        patch.object(App, "_start_background_maintenance"),
        patch.object(App, "_offer_shared_installer"),
    ):
        app = App(root, database)
        try:
            dialog = DiagnosticDialog(root, app)
            wait(root, lambda: not dialog._busy)
            with database.session() as connection:
                connection.execute("DELETE FROM product_search")
            dialog.run_diagnostic()
            wait(root, lambda: not dialog._busy)
            assert "Index de recherche : À RÉPARER" in dialog.report
            original_rebuild = database.rebuild_search
            release = threading.Event()
            worker_started = threading.Event()
            threads = []

            def delayed_rebuild(**kwargs):
                threads.append(threading.get_ident())
                worker_started.set()
                assert release.wait(5), "Le thread Tk ne répond plus"
                return original_rebuild(**kwargs)

            with patch.object(
                database, "rebuild_search", side_effect=delayed_rebuild
            ) as rebuild:
                dialog.repair_button.invoke()
                assert worker_started.wait(2)
                assert dialog._busy
                assert str(dialog.repair_button["state"]) == "disabled"
                dialog.repair_index()  # Pas de seconde reconstruction concurrente.
                root.after(20, release.set)
                wait(root, lambda: not dialog._busy)
                assert rebuild.call_count == 1
            assert len(threads) == 1 and threads[0] != threading.get_ident()
            assert "Index reconstruit et testé" in dialog.status["text"]
            assert "Articles reconstruits : 1 / 1" in dialog.report
            assert str(dialog.export_button["state"]) == "normal"
            dialog.geometry("700x480")
            root.update()
            for button in (
                dialog.repair_button,
                dialog.export_button,
                dialog.copy_button,
                dialog.refresh_button,
            ):
                assert button.winfo_ismapped()
                assert button.winfo_width() >= button.winfo_reqwidth()
            assert database.search_products_detailed("gant").rows[0]["id"] == product

            with patch.object(
                database,
                "_create_search_table",
                side_effect=sqlite3.OperationalError("database is locked"),
            ):
                dialog.repair_button.invoke()
                wait(root, lambda: not dialog._busy)
            assert "Échec de reconstruction" in dialog.status["text"]
            assert "base est occupée" in dialog.report
            assert str(dialog.repair_button["state"]) == "normal"

            with patch.object(
                database, "rebuild_search", side_effect=RuntimeError("NE_PAS_EXPORTER")
            ):
                dialog.repair_button.invoke()
                wait(root, lambda: not dialog._busy)
            assert "RuntimeError" in dialog.report
            assert "NE_PAS_EXPORTER" not in dialog.report
            assert str(dialog.repair_button["state"]) == "normal"

            # Fermer la fenêtre n'autorise aucun accès Tk depuis le worker.
            release.clear()
            worker_started.clear()
            finished = threading.Event()

            def close_during_repair(**kwargs):
                try:
                    return delayed_rebuild(**kwargs)
                finally:
                    finished.set()

            with (
                patch.object(
                    database, "rebuild_search", side_effect=close_during_repair
                ),
                patch.object(
                    dialog, "show_report", wraps=dialog.show_report
                ) as delivered,
            ):
                dialog.repair_button.invoke()
                assert worker_started.wait(2)
                dialog.destroy()
                release.set()
                wait(root, finished.is_set)
                wait(root, lambda: delivered.call_count == 1)
            assert not errors, repr(errors)
        finally:
            app.close(force=True)


if __name__ == "__main__":
    main()
