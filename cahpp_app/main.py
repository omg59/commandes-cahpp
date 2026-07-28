from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from .database import Database
from .paths import DATABASE_PATH, ensure_directories
from .ui import App


def main() -> None:
    ensure_directories()
    root = tk.Tk()
    try:
        database = Database(DATABASE_PATH)
        App(root, database)
        root.mainloop()
    except Exception as exc:
        messagebox.showerror(
            "Commandes CAHPP",
            f"L'application n'a pas pu démarrer :\n{exc}",
            parent=root,
        )
        raise

