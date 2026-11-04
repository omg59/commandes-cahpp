"""Construit et visite les pages dans un processus et un dossier isolés."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class InterfaceSmokeTest(unittest.TestCase):
    def test_all_pages_construct_and_refresh_without_callback_errors(self):
        if (sys.platform != "win32" and not os.environ.get("DISPLAY")
                and os.environ.get("CAHPP_REQUIRE_GUI") != "1"):
            self.skipTest("Pas d'écran : utiliser xvfb-run ou CAHPP_REQUIRE_GUI=1 en CI.")
        script = textwrap.dedent('''
            import time
            import tkinter as tk
            from unittest.mock import patch
            from cahpp_app.database import Database
            from cahpp_app.paths import DATABASE_PATH
            from cahpp_app.ui import App

            database = Database(DATABASE_PATH)
            database.save_settings({"user_name": "Test", "user_id": "test",
                                    "collaboration_enabled": "0"})
            root = tk.Tk()
            errors = []
            root.report_callback_exception = lambda *args: errors.append(args)
            with patch.object(App, "_start_background_maintenance"), \\
                 patch.object(App, "_offer_shared_installer"), \\
                 patch("cahpp_app.ui.messagebox.showerror") as error_box, \\
                 patch("cahpp_app.ui.messagebox.showwarning") as warning_box:
                app = App(root, database)
                try:
                    for page in app.pages:
                        app.show_page(page)
                        root.update()
                    app.show_page("catalog")
                    catalog = app.pages["catalog"]
                    catalog.search_var.set("compresse")
                    catalog.search(force=True)
                    deadline = time.monotonic() + 5
                    while catalog._search_pending and time.monotonic() < deadline:
                        root.update()
                        time.sleep(0.01)
                    assert not catalog._search_pending, "Recherche bloquée"
                    root.update()

                    app.show_page("new_order")
                    order_page = app.pages["new_order"]
                    order_page._show_supplier_suggestions(["FOURNISSEUR TEST"])
                    order_page.supplier_suggestions.focus_force()
                    root.update()
                    order_page._hide_supplier_suggestions_if_unused()
                    assert order_page._supplier_matches

                    # Reproduit une fenêtre Tcl native inconnue du registre Python,
                    # comme la liste déroulante interne d'un ttk.Combobox Windows.
                    root.tk.call("entry", ".native_focus")
                    # Le runner Windows peut refuser le focus d'une fenêtre native.
                    # Contrôler la réponse Tcl conserve le vrai nametowidget Python
                    # et reproduit le KeyError sans dépendre du bureau du runner.
                    root.tk.call("rename", "focus", "_test_original_focus")
                    root.tk.call("proc", "focus", "args", "return .native_focus")
                    try:
                        try:
                            root.focus_get()
                        except KeyError:
                            pass
                        else:
                            raise AssertionError("Le scénario doit reproduire le KeyError")
                        order_page._hide_supplier_suggestions_if_unused()
                        assert not order_page._supplier_matches
                    finally:
                        root.tk.call("rename", "focus", "")
                        root.tk.call("rename", "_test_original_focus", "focus")
                        root.tk.call("destroy", ".native_focus")

                    assert not errors, repr(errors)
                    error_box.assert_not_called()
                    warning_box.assert_not_called()
                finally:
                    app.close()
        ''')
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, CAHPP_PORTABLE_ROOT=directory)
            result = subprocess.run(
                [sys.executable, "-c", script], env=env,
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True, text=True, timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
