from __future__ import annotations

import tkinter as tk
import logging
from tkinter import messagebox

from . import __version__
from .app_logging import configure_logging, install_exception_hooks, log_failure
from .paths import DATABASE_PATH, ensure_directories


def main() -> None:
    configure_logging()
    install_exception_hooks()
    logger = logging.getLogger(__name__)
    logger.info("demarrage version=%s", __version__)
    root = None
    try:
        from .database import Database
        from .ui import App

        ensure_directories()
        root = tk.Tk()

        def callback_error(kind, error, tb):
            log_failure(logger, "interface_exception", error.with_traceback(tb))
            messagebox.showerror(
                "Erreur dans l'application",
                "L'action n'a pas pu être terminée. Consultez Paramètres > "
                "Diagnostic pour récupérer le rapport technique.", parent=root,
            )

        root.report_callback_exception = callback_error
        database = Database(DATABASE_PATH)
        App(root, database)
        root.mainloop()
    except Exception as exc:
        log_failure(logger, "demarrage_echec", exc)
        if root is None:
            raise
        messagebox.showerror(
            "Commandes CAHPP",
            f"L'application n'a pas pu démarrer :\n{exc}",
            parent=root,
        )
        raise
    finally:
        logger.info("arret")

