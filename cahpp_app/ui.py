from __future__ import annotations

import os
import queue
import re
import subprocess
import threading
import tkinter as tk
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable

from .catalog_importer import CatalogImporter, ImportResult
from .database import Database
from .paths import BACKUP_DIR, EXPORT_DIR
from .pdf_export import generate_order_pdf


COLORS = {
    "nav": "#123A5A",
    "nav_hover": "#1A5276",
    "accent": "#1F6F9F",
    "accent_light": "#E8F2F8",
    "background": "#F3F6F8",
    "surface": "#FFFFFF",
    "text": "#1E2933",
    "muted": "#64748B",
    "border": "#D8E1E8",
    "success": "#277A53",
    "warning": "#A36400",
    "danger": "#A33A3A",
}


def format_number(value: object, decimals: int = 0) -> str:
    if value in (None, ""):
        return "—"
    number = Decimal(str(value))
    if decimals == 0 and number == number.to_integral():
        return f"{int(number):,}".replace(",", " ")
    text = f"{number:.{decimals}f}".replace(".", ",")
    return text


def format_price(value: object, decimals: int = 4) -> str:
    if value is None:
        return "Prix absent"
    return f"{Decimal(str(value)):.{decimals}f}".replace(".", ",") + " €"


def open_path(path: Path | str) -> None:
    path = str(path)
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", path])


def safe_filename(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*]+', "-", value)
    value = re.sub(r"\s+", " ", value).strip(" .-")
    return value or "fournisseur"


def filter_supplier_names(names: list[str], query: str) -> list[str]:
    query = query.strip().casefold()
    if not query:
        return names
    return [name for name in names if query in name.casefold()]


def configured_pdf_directory(database: Database) -> Path:
    configured = database.get_settings().get("pdf_default_directory", "").strip()
    if configured:
        directory = Path(os.path.expandvars(configured)).expanduser()
        if directory.is_dir():
            return directory
    return EXPORT_DIR


def suggested_pdf_filename(database: Database, order) -> str:
    sequence = database.daily_supplier_order_sequence(int(order["id"]))
    suffix = "" if sequence == 1 else f"_{sequence}"
    supplier = safe_filename(str(order["supplier_name"]).title())
    return f"BC-{order['order_date']}{suffix}_{supplier}.pdf"


def choose_pdf_path(parent, database: Database, order) -> Path | None:
    default_name = suggested_pdf_filename(database, order)
    selected = filedialog.asksaveasfilename(
        parent=parent,
        title="Enregistrer le bon de commande",
        initialdir=str(configured_pdf_directory(database)),
        initialfile=default_name,
        defaultextension=".pdf",
        filetypes=[("Document PDF", "*.pdf"), ("Tous les fichiers", "*.*")],
    )
    return Path(selected) if selected else None


class App(ttk.Frame):
    def __init__(self, root: tk.Tk, database: Database):
        super().__init__(root)
        self.root = root
        self.database = database
        self.root.title("Commandes CAHPP")
        self.root.geometry("1320x820")
        self.root.minsize(1060, 680)
        self._configure_styles()
        self.pack(fill="both", expand=True)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.sidebar = tk.Frame(self, bg=COLORS["nav"], width=210)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.content = tk.Frame(self, bg=COLORS["background"])
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.rowconfigure(0, weight=1)
        self.content.columnconfigure(0, weight=1)

        tk.Label(
            self.sidebar,
            text="COMMANDES\nCAHPP",
            bg=COLORS["nav"],
            fg="white",
            font=("Segoe UI Semibold", 17),
            justify="left",
            padx=20,
            pady=22,
        ).pack(fill="x")

        self.pages: dict[str, BasePage] = {}
        definitions = [
            ("dashboard", "Vue d'ensemble", DashboardPage),
            ("catalog", "Catalogue", CatalogPage),
            ("new_order", "Nouvelle commande", OrderPage),
            ("orders", "Historique", OrdersPage),
            ("suppliers", "Fournisseurs", SuppliersPage),
            ("import", "Mise à jour CAHPP", ImportPage),
            ("settings", "Paramètres", SettingsPage),
        ]
        for key, label, page_class in definitions:
            button = tk.Button(
                self.sidebar,
                text=label,
                anchor="w",
                bg=COLORS["nav"],
                activebackground=COLORS["nav_hover"],
                fg="white",
                activeforeground="white",
                bd=0,
                highlightthickness=0,
                font=("Segoe UI", 10),
                padx=20,
                pady=11,
                command=lambda selected=key: self.show_page(selected),
            )
            button.pack(fill="x")
            page = page_class(self.content, self)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = page

        tk.Label(
            self.sidebar,
            text="Local • hors ligne",
            bg=COLORS["nav"],
            fg="#BDD6E5",
            font=("Segoe UI", 8),
            padx=20,
            pady=16,
            anchor="w",
        ).pack(side="bottom", fill="x")
        self.show_page("dashboard")

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure(
            "TFrame",
            background=COLORS["background"],
        )
        style.configure(
            "Surface.TFrame",
            background=COLORS["surface"],
        )
        style.configure(
            "TLabel",
            background=COLORS["background"],
            foreground=COLORS["text"],
            font=("Segoe UI", 9),
        )
        style.configure(
            "Surface.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["text"],
        )
        style.configure(
            "Title.TLabel",
            font=("Segoe UI Semibold", 20),
            foreground=COLORS["text"],
        )
        style.configure(
            "Subtitle.TLabel",
            font=("Segoe UI", 10),
            foreground=COLORS["muted"],
        )
        style.configure(
            "Accent.TButton",
            font=("Segoe UI Semibold", 9),
            padding=(12, 7),
        )
        style.configure("TButton", font=("Segoe UI", 9), padding=(9, 6))
        style.configure(
            "Treeview",
            font=("Segoe UI", 9),
            rowheight=28,
            background="white",
            fieldbackground="white",
            bordercolor=COLORS["border"],
        )
        style.configure(
            "Treeview.Heading",
            font=("Segoe UI Semibold", 9),
            padding=(6, 7),
        )
        style.configure("TEntry", padding=5)
        style.configure("TCombobox", padding=4)

    def show_page(self, name: str) -> None:
        page = self.pages[name]
        page.tkraise()
        page.refresh()

    def refresh_pages(self) -> None:
        for page in self.pages.values():
            page.invalidate()


class BasePage(ttk.Frame):
    def __init__(self, parent, app: App):
        super().__init__(parent, padding=22)
        self.app = app
        self.database = app.database
        self._valid = False

    def header(self, title: str, subtitle: str) -> None:
        ttk.Label(self, text=title, style="Title.TLabel").pack(anchor="w")
        ttk.Label(self, text=subtitle, style="Subtitle.TLabel").pack(
            anchor="w", pady=(2, 18)
        )

    def invalidate(self) -> None:
        self._valid = False

    def refresh(self) -> None:
        self._valid = True


class DashboardPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header(
            "Vue d'ensemble",
            "Catalogue, fournisseurs et commandes disponibles sur ce poste.",
        )
        self.cards = ttk.Frame(self)
        self.cards.pack(fill="x")
        self.card_values: dict[str, tk.Label] = {}
        for index, (key, label) in enumerate(
            [
                ("products", "Articles actifs"),
                ("suppliers", "Fournisseurs"),
                ("favorites", "Articles favoris"),
                ("orders", "Commandes"),
            ]
        ):
            card = tk.Frame(
                self.cards,
                bg=COLORS["surface"],
                highlightbackground=COLORS["border"],
                highlightthickness=1,
                padx=16,
                pady=14,
            )
            card.grid(row=0, column=index, sticky="ew", padx=(0, 12))
            self.cards.columnconfigure(index, weight=1)
            value = tk.Label(
                card,
                text="0",
                bg=COLORS["surface"],
                fg=COLORS["accent"],
                font=("Segoe UI Semibold", 22),
                anchor="w",
            )
            value.pack(fill="x")
            tk.Label(
                card,
                text=label,
                bg=COLORS["surface"],
                fg=COLORS["muted"],
                font=("Segoe UI", 9),
                anchor="w",
            ).pack(fill="x")
            self.card_values[key] = value

        self.import_box = tk.Frame(
            self,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        self.import_box.pack(fill="x", pady=(20, 0))
        self.import_label = tk.Label(
            self.import_box,
            text="Aucun catalogue importé",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=("Segoe UI Semibold", 11),
            anchor="w",
        )
        self.import_label.pack(fill="x")
        self.import_detail = tk.Label(
            self.import_box,
            text="",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
            anchor="w",
        )
        self.import_detail.pack(fill="x", pady=(4, 0))

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(20, 0))
        ttk.Button(
            actions,
            text="Préparer une commande",
            style="Accent.TButton",
            command=lambda: self.app.show_page("new_order"),
        ).pack(side="left")
        ttk.Button(
            actions,
            text="Importer un catalogue",
            command=lambda: self.app.show_page("import"),
        ).pack(side="left", padx=8)

    def refresh(self) -> None:
        stats = self.database.dashboard_stats()
        for key, label in self.card_values.items():
            label.configure(text=f"{int(stats[key]):,}".replace(",", " "))
        latest = stats["latest_import"]
        if latest:
            when = datetime.fromisoformat(latest["imported_at"]).strftime(
                "%d/%m/%Y à %H:%M"
            )
            self.import_label.configure(text=latest["filename"])
            self.import_detail.configure(
                text=f"Dernier import le {when} • "
                f"{int(latest['row_count']):,} articles".replace(",", " ")
            )
        else:
            self.import_label.configure(text="Aucun catalogue importé")
            self.import_detail.configure(
                text="Commencez par importer la base tarifaire CAHPP."
            )
        self._valid = True


class CatalogPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header(
            "Catalogue",
            "Recherche par désignation, fournisseur, référence ou code CAHPP.",
        )
        filters = ttk.Frame(self)
        filters.pack(fill="x", pady=(0, 10))
        ttk.Label(filters, text="Recherche").pack(side="left")
        self.search_var = tk.StringVar()
        search = ttk.Entry(filters, textvariable=self.search_var, width=38)
        search.pack(side="left", padx=(7, 14))
        search.bind("<KeyRelease>", self._schedule_search)
        ttk.Label(filters, text="Fournisseur").pack(side="left")
        self.supplier_var = tk.StringVar()
        self.supplier_box = ttk.Combobox(
            filters,
            textvariable=self.supplier_var,
            state="readonly",
            width=30,
        )
        self.supplier_box.pack(side="left", padx=7)
        self.supplier_box.bind("<<ComboboxSelected>>", lambda event: self.search())
        self.favorite_var = tk.BooleanVar()
        ttk.Checkbutton(
            filters,
            text="Favoris uniquement",
            variable=self.favorite_var,
            command=self.search,
        ).pack(side="left", padx=10)
        ttk.Button(filters, text="Rechercher", command=self.search).pack(
            side="right"
        )

        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True)
        columns = (
            "favorite",
            "supplier",
            "reference",
            "code",
            "designation",
            "pack",
            "price",
            "vat",
        )
        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        headings = {
            "favorite": "★",
            "supplier": "Fournisseur",
            "reference": "Référence",
            "code": "Code CAHPP",
            "designation": "Désignation",
            "pack": "Cond.",
            "price": "PU HT",
            "vat": "TVA",
        }
        widths = {
            "favorite": 38,
            "supplier": 150,
            "reference": 95,
            "code": 90,
            "designation": 480,
            "pack": 65,
            "price": 85,
            "vat": 55,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(
                column,
                width=widths[column],
                minwidth=35,
                stretch=column == "designation",
                anchor="center" if column not in ("supplier", "designation") else "w",
            )
        scrollbar = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda event: self.toggle_favorite())

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", pady=(10, 0))
        self.result_label = ttk.Label(
            bottom, text="", style="Subtitle.TLabel"
        )
        self.result_label.pack(side="left")
        ttk.Button(
            bottom,
            text="Ajouter / retirer des favoris",
            command=self.toggle_favorite,
        ).pack(side="right")
        ttk.Button(
            bottom,
            text="Configurer le favori",
            command=self.edit_favorite,
        ).pack(side="right", padx=8)
        ttk.Button(
            bottom,
            text="Commander cet article",
            style="Accent.TButton",
            command=self.start_order,
        ).pack(side="right")

        self.supplier_map: dict[str, int | None] = {}
        self._after_id = None

    def _schedule_search(self, event=None) -> None:
        if self._after_id:
            self.after_cancel(self._after_id)
        self._after_id = self.after(300, self.search)

    def _load_suppliers(self) -> None:
        suppliers = self.database.list_suppliers(used_only=True)
        self.supplier_map = {"Tous les fournisseurs": None}
        self.supplier_map.update({row["name"]: row["id"] for row in suppliers})
        values = list(self.supplier_map)
        current = self.supplier_var.get()
        self.supplier_box["values"] = values
        if current not in self.supplier_map:
            self.supplier_var.set(values[0] if values else "")

    def search(self) -> None:
        supplier_id = self.supplier_map.get(self.supplier_var.get())
        rows = self.database.search_products(
            query=self.search_var.get(),
            supplier_id=supplier_id,
            favorite_only=self.favorite_var.get(),
            limit=300,
        )
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            designation = row["short_name"] or row["designation"]
            self.tree.insert(
                "",
                "end",
                iid=str(row["id"]),
                values=(
                    "★" if row["favorite"] else "",
                    row["supplier_name"],
                    row["supplier_ref"],
                    row["code_cahpp"],
                    designation,
                    format_number(row["conditionnement"]),
                    format_price(row["unit_price"]),
                    format_number(row["vat"], 1) + " %",
                ),
            )
        suffix = " (limite 300)" if len(rows) == 300 else ""
        self.result_label.configure(
            text=f"{len(rows)} résultat(s){suffix}"
        )

    def selected_product_id(self) -> int | None:
        selected = self.tree.selection()
        return int(selected[0]) if selected else None

    def toggle_favorite(self) -> None:
        product_id = self.selected_product_id()
        if not product_id:
            return
        product = self.database.get_product(product_id)
        self.database.set_favorite(product_id, not bool(product["favorite"]))
        self.search()
        self.app.pages["dashboard"].invalidate()

    def edit_favorite(self) -> None:
        product_id = self.selected_product_id()
        if not product_id:
            messagebox.showinfo(
                "Favori", "Sélectionnez d'abord un article.", parent=self
            )
            return
        product = self.database.get_product(product_id)
        usual = simpledialog.askfloat(
            "Quantité habituelle",
            "Nombre habituel de cartons :",
            initialvalue=float(product["usual_cartons"] or 1),
            minvalue=0.001,
            parent=self,
        )
        if usual is None:
            return
        short_name = simpledialog.askstring(
            "Désignation courte",
            "Désignation affichée dans les commandes :",
            initialvalue=product["short_name"] or product["designation"],
            parent=self,
        )
        self.database.set_favorite(
            product_id, True, usual_cartons=usual, short_name=short_name or ""
        )
        self.search()

    def start_order(self) -> None:
        product_id = self.selected_product_id()
        if not product_id:
            messagebox.showinfo(
                "Commande",
                "Sélectionnez d'abord un article du catalogue.",
                parent=self,
            )
            return
        self.app.show_page("new_order")
        order_page: OrderPage = self.app.pages["new_order"]  # type: ignore[assignment]
        order_page.start_with_product(product_id)

    def refresh(self) -> None:
        self._load_suppliers()
        self.search()
        self._valid = True


class OrderPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header(
            "Nouvelle commande",
            "Choisissez un fournisseur, ajoutez les produits, puis générez le bon.",
        )
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text="Fournisseur (saisir pour filtrer)").pack(side="left")
        self.supplier_var = tk.StringVar()
        self.supplier_box = ttk.Combobox(
            top,
            textvariable=self.supplier_var,
            state="normal",
            width=40,
        )
        self.supplier_box.pack(side="left", padx=(7, 16))
        self.supplier_box.bind(
            "<<ComboboxSelected>>", lambda event: self.supplier_changed()
        )
        self.supplier_box.bind("<KeyRelease>", self._filter_suppliers)
        self.franco_label = ttk.Label(top, text="", style="Subtitle.TLabel")
        self.franco_label.pack(side="left")
        self.mode_label = ttk.Label(top, text="", style="Subtitle.TLabel")
        self.mode_label.pack(side="right", padx=(8, 0))
        ttk.Button(
            top,
            text="Nouvelle / vider",
            command=self.reset_order,
        ).pack(side="right")

        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left = ttk.Frame(panes, style="Surface.TFrame", padding=12)
        right = ttk.Frame(panes, style="Surface.TFrame", padding=12)
        panes.add(left, weight=1)
        panes.add(right, weight=2)

        ttk.Label(
            left, text="Articles disponibles", style="Surface.TLabel"
        ).pack(anchor="w")
        search_row = ttk.Frame(left, style="Surface.TFrame")
        search_row.pack(fill="x", pady=(8, 8))
        self.product_search_var = tk.StringVar()
        search_entry = ttk.Entry(
            search_row, textvariable=self.product_search_var
        )
        search_entry.pack(side="left", fill="x", expand=True)
        search_entry.bind("<KeyRelease>", self._schedule_search)
        ttk.Button(
            search_row, text="Chercher", command=self.search_products
        ).pack(side="left", padx=(6, 0))

        self.product_tree = ttk.Treeview(
            left,
            columns=("ref", "designation", "pack", "price"),
            show="headings",
            selectmode="browse",
            height=14,
        )
        for column, title, width in (
            ("ref", "Référence", 90),
            ("designation", "Désignation", 260),
            ("pack", "Cond.", 55),
            ("price", "PU HT", 75),
        ):
            self.product_tree.heading(column, text=title)
            self.product_tree.column(
                column,
                width=width,
                stretch=column == "designation",
                anchor="w" if column == "designation" else "center",
            )
        self.product_tree.pack(fill="both", expand=True)
        self.product_tree.bind("<Double-1>", lambda event: self.add_product())
        left_buttons = ttk.Frame(left, style="Surface.TFrame")
        left_buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(
            left_buttons,
            text="Ajouter à la commande",
            style="Accent.TButton",
            command=self.add_product,
        ).pack(side="left")
        ttk.Button(
            left_buttons,
            text="Article hors catalogue",
            command=self.add_manual_product,
        ).pack(side="right")

        ttk.Label(
            right, text="Contenu de la commande", style="Surface.TLabel"
        ).pack(anchor="w")
        self.cart_tree = ttk.Treeview(
            right,
            columns=("designation", "ref", "cartons", "pack", "price", "total"),
            show="headings",
            selectmode="browse",
            height=15,
        )
        for column, title, width in (
            ("designation", "Désignation", 270),
            ("ref", "Réf.", 90),
            ("cartons", "Cartons", 65),
            ("pack", "Unités/carton", 85),
            ("price", "PU HT", 75),
            ("total", "Total HT", 85),
        ):
            self.cart_tree.heading(column, text=title)
            self.cart_tree.column(
                column,
                width=width,
                stretch=column == "designation",
                anchor="w" if column == "designation" else "center",
            )
        self.cart_tree.pack(fill="both", expand=True, pady=(8, 0))
        self.cart_tree.bind("<Double-1>", lambda event: self.edit_quantity())

        cart_buttons = ttk.Frame(right, style="Surface.TFrame")
        cart_buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(
            cart_buttons, text="Modifier la quantité", command=self.edit_quantity
        ).pack(side="left")
        ttk.Button(
            cart_buttons, text="Retirer", command=self.remove_line
        ).pack(side="left", padx=6)
        self.total_label = tk.Label(
            cart_buttons,
            text="Total HT : 0,00 €",
            bg=COLORS["surface"],
            fg=COLORS["accent"],
            font=("Segoe UI Semibold", 12),
        )
        self.total_label.pack(side="right")

        notes_frame = ttk.Frame(self)
        notes_frame.pack(fill="x", pady=(10, 0))
        ttk.Label(notes_frame, text="Note").pack(side="left")
        self.notes_var = tk.StringVar()
        ttk.Entry(notes_frame, textvariable=self.notes_var).pack(
            side="left", fill="x", expand=True, padx=8
        )
        ttk.Button(
            notes_frame,
            text="Enregistrer le brouillon",
            command=self.save_draft,
        ).pack(side="right")
        ttk.Button(
            notes_frame,
            text="Générer le PDF",
            style="Accent.TButton",
            command=self.save_and_generate,
        ).pack(side="right", padx=(0, 8))

        self.supplier_map: dict[str, int] = {}
        self._all_supplier_names: list[str] = []
        self.cart: list[dict[str, object]] = []
        self._search_after = None
        self._previous_supplier = ""
        self.current_order_id: int | None = None
        self.current_order_date: date | None = None

    def _schedule_search(self, event=None) -> None:
        if self._search_after:
            self.after_cancel(self._search_after)
        self._search_after = self.after(250, self.search_products)

    def load_suppliers(self) -> None:
        suppliers = self.database.list_suppliers(used_only=True)
        self.supplier_map = {row["name"]: row["id"] for row in suppliers}
        self._all_supplier_names = list(self.supplier_map)
        self.supplier_box["values"] = self._all_supplier_names
        if self.supplier_var.get() not in self.supplier_map:
            self.supplier_var.set("")

    def _filter_suppliers(self, event=None) -> None:
        if event and event.keysym in {
            "Up",
            "Down",
            "Left",
            "Right",
            "Escape",
            "Tab",
            "Shift_L",
            "Shift_R",
        }:
            return
        matches = filter_supplier_names(
            self._all_supplier_names, self.supplier_var.get()
        )
        self.supplier_box["values"] = matches
        if event and event.keysym == "Return":
            if self.supplier_var.get() in self.supplier_map:
                self.supplier_changed()
            elif len(matches) == 1:
                self.supplier_var.set(matches[0])
                self.supplier_changed()
            return

    def selected_supplier_id(self) -> int | None:
        return self.supplier_map.get(self.supplier_var.get())

    def supplier_changed(self) -> None:
        if self.cart:
            if not messagebox.askyesno(
                "Changer de fournisseur",
                "Le contenu actuel de la commande sera effacé. Continuer ?",
                parent=self,
            ):
                self.supplier_var.set(self._previous_supplier)
                return
            self.cart.clear()
            self.refresh_cart()
        self._previous_supplier = self.supplier_var.get()
        supplier_id = self.selected_supplier_id()
        supplier = self.database.get_supplier(supplier_id) if supplier_id else None
        if supplier and supplier["franco_ht"] is not None:
            self.franco_label.configure(
                text=f"Franco : {format_price(supplier['franco_ht'], 2)} HT"
            )
        else:
            self.franco_label.configure(text="Franco non renseigné")
        self.search_products()

    def search_products(self) -> None:
        supplier_id = self.selected_supplier_id()
        self.product_tree.delete(*self.product_tree.get_children())
        if not supplier_id:
            return
        rows = self.database.search_products(
            query=self.product_search_var.get(),
            supplier_id=supplier_id,
            favorite_only=not bool(self.product_search_var.get().strip()),
            limit=200,
        )
        if not rows and not self.product_search_var.get().strip():
            rows = self.database.search_products(
                supplier_id=supplier_id, favorite_only=False, limit=100
            )
        for row in rows:
            self.product_tree.insert(
                "",
                "end",
                iid=str(row["id"]),
                values=(
                    row["supplier_ref"],
                    row["short_name"] or row["designation"],
                    format_number(row["conditionnement"]),
                    format_price(row["unit_price"]),
                ),
            )

    def add_product(self) -> None:
        selected = self.product_tree.selection()
        if not selected:
            return
        self.add_product_by_id(int(selected[0]))

    def add_product_by_id(self, product_id: int) -> None:
        product = self.database.get_product(product_id)
        if product is None:
            return
        if product["unit_price"] is None:
            price = simpledialog.askfloat(
                "Prix manquant",
                "Cet article n'a pas de prix CAHPP. Indiquez le prix unitaire HT :",
                minvalue=0,
                parent=self,
            )
            if price is None:
                return
        else:
            price = float(product["unit_price"])
        cartons = simpledialog.askfloat(
            "Quantité",
            "Nombre de cartons à commander :",
            initialvalue=float(product["usual_cartons"] or 1),
            minvalue=0.001,
            parent=self,
        )
        if cartons is None:
            return
        conditionnement = product["conditionnement"] or product["qml"] or 1
        if (
            product["conditionnement"] is not None
            and product["qml"] is not None
            and float(product["conditionnement"]) != float(product["qml"])
        ):
            selected_pack = simpledialog.askfloat(
                "Conditionnement à confirmer",
                "Le catalogue indique deux valeurs différentes :\n"
                f"Conditionnement : {format_number(product['conditionnement'])}\n"
                f"Qml : {format_number(product['qml'])}\n\n"
                "Nombre d'unités à utiliser par carton :",
                initialvalue=float(product["conditionnement"]),
                minvalue=0.001,
                parent=self,
            )
            if selected_pack is None:
                return
            conditionnement = selected_pack
        existing = next(
            (
                item
                for item in self.cart
                if item["product_id"] == int(product["id"])
            ),
            None,
        )
        if existing:
            existing["cartons"] = float(existing["cartons"]) + cartons
        else:
            self.cart.append(
                {
                    "product_id": int(product["id"]),
                    "code_cahpp": product["code_cahpp"],
                    "supplier_ref": product["supplier_ref"],
                    "designation": product["short_name"]
                    or product["designation"],
                    "cartons": cartons,
                    "units_per_carton": float(conditionnement),
                    "unit_price": price,
                    "vat": float(product["vat"] or 0),
                }
            )
        self.refresh_cart()

    def start_with_product(self, product_id: int) -> None:
        product = self.database.get_product(product_id)
        if product is None:
            return
        if not self.reset_order(confirm=True):
            return
        self.supplier_var.set(product["supplier_name"])
        self._previous_supplier = product["supplier_name"]
        self.supplier_changed()
        self.add_product_by_id(product_id)

    def add_manual_product(self) -> None:
        supplier_id = self.selected_supplier_id()
        if not supplier_id:
            messagebox.showinfo(
                "Article",
                "Choisissez d'abord un fournisseur.",
                parent=self,
            )
            return
        dialog = ManualProductDialog(self, self.database, supplier_id)
        self.wait_window(dialog)
        if dialog.product_id:
            self.search_products()
            self.product_tree.selection_set(str(dialog.product_id))
            self.add_product()

    def refresh_cart(self) -> None:
        self.cart_tree.delete(*self.cart_tree.get_children())
        total = Decimal("0")
        for index, item in enumerate(self.cart):
            line_total = (
                Decimal(str(item["cartons"]))
                * Decimal(str(item["units_per_carton"]))
                * Decimal(str(item["unit_price"]))
            )
            total += line_total
            self.cart_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    item["designation"],
                    item["supplier_ref"],
                    format_number(item["cartons"]),
                    format_number(item["units_per_carton"]),
                    format_price(item["unit_price"]),
                    format_price(line_total, 2),
                ),
            )
        self.total_label.configure(text=f"Total HT : {format_price(total, 2)}")
        supplier_id = self.selected_supplier_id()
        supplier = self.database.get_supplier(supplier_id) if supplier_id else None
        if supplier and supplier["franco_ht"] is not None:
            difference = Decimal(str(supplier["franco_ht"])) - total
            if difference > 0:
                self.franco_label.configure(
                    text=f"Franco : il manque {format_price(difference, 2)}",
                    foreground=COLORS["warning"],
                )
            else:
                self.franco_label.configure(
                    text="Franco atteint",
                    foreground=COLORS["success"],
                )

    def edit_quantity(self) -> None:
        selected = self.cart_tree.selection()
        if not selected:
            return
        index = int(selected[0])
        item = self.cart[index]
        quantity = simpledialog.askfloat(
            "Quantité",
            "Nombre de cartons :",
            initialvalue=float(item["cartons"]),
            minvalue=0.001,
            parent=self,
        )
        if quantity is not None:
            item["cartons"] = quantity
            self.refresh_cart()

    def remove_line(self) -> None:
        selected = self.cart_tree.selection()
        if selected:
            self.cart.pop(int(selected[0]))
            self.refresh_cart()

    def load_order(self, order_id: int) -> None:
        order, lines = self.database.get_order(order_id)
        if order["status"] != "Brouillon":
            raise ValueError("Seuls les brouillons peuvent être modifiés.")
        self.current_order_id = order_id
        self.current_order_date = date.fromisoformat(order["order_date"])
        self.supplier_var.set(order["supplier_name"])
        self._previous_supplier = order["supplier_name"]
        self.notes_var.set(order["notes"] or "")
        self.cart = [
            {
                "product_id": line["product_id"],
                "code_cahpp": line["code_cahpp"],
                "supplier_ref": line["supplier_ref"],
                "designation": line["designation"],
                "cartons": line["cartons"],
                "units_per_carton": line["units_per_carton"],
                "unit_price": line["unit_price"],
                "vat": line["vat"],
            }
            for line in lines
        ]
        self.mode_label.configure(
            text=f"Modification de {order['order_number']}"
        )
        supplier = self.database.get_supplier(order["supplier_id"])
        if supplier and supplier["franco_ht"] is not None:
            self.franco_label.configure(
                text=f"Franco : {format_price(supplier['franco_ht'], 2)} HT"
            )
        else:
            self.franco_label.configure(text="Franco non renseigné")
        self.search_products()
        self.refresh_cart()

    def reset_order(self, confirm: bool = True) -> bool:
        if confirm and (self.cart or self.current_order_id):
            if not messagebox.askyesno(
                "Nouvelle commande",
                "Effacer la commande affichée et repartir de zéro ?",
                parent=self,
            ):
                return False
        self.current_order_id = None
        self.current_order_date = None
        self.cart.clear()
        self.notes_var.set("")
        self.supplier_var.set("")
        self._previous_supplier = ""
        self.mode_label.configure(text="")
        self.franco_label.configure(text="")
        self.product_tree.delete(*self.product_tree.get_children())
        self.refresh_cart()
        return True

    def _save(self, generate_pdf: bool) -> None:
        supplier_id = self.selected_supplier_id()
        if not supplier_id:
            messagebox.showwarning(
                "Commande", "Choisissez un fournisseur.", parent=self
            )
            return
        if not self.cart:
            messagebox.showwarning(
                "Commande", "Ajoutez au moins un article.", parent=self
            )
            return
        editing_order_id = self.current_order_id
        order_id = self.database.save_order(
            supplier_id=supplier_id,
            lines=self.cart,
            notes=self.notes_var.get(),
            order_id=editing_order_id,
            selected_date=self.current_order_date,
        )
        order, _ = self.database.get_order(order_id)
        self.current_order_id = order_id
        self.current_order_date = date.fromisoformat(order["order_date"])
        self.mode_label.configure(
            text=f"Modification de {order['order_number']}"
        )
        if generate_pdf:
            output = choose_pdf_path(self, self.database, order)
            if output is None:
                messagebox.showinfo(
                    "PDF non généré",
                    "L'enregistrement du PDF a été annulé. "
                    "La commande reste enregistrée comme brouillon.",
                    parent=self,
                )
                self.app.refresh_pages()
                return
            generate_order_pdf(self.database, order_id, output)
            messagebox.showinfo(
                "Bon généré",
                f"Le bon de commande a été créé :\n{output}",
                parent=self,
            )
            open_path(output.parent)
        else:
            messagebox.showinfo(
                "Commande",
                (
                    "Le brouillon a été mis à jour."
                    if editing_order_id
                    else "Le brouillon a été enregistré."
                ),
                parent=self,
            )
        self.reset_order(confirm=False)
        self.app.refresh_pages()

    def save_draft(self) -> None:
        self._save(generate_pdf=False)

    def save_and_generate(self) -> None:
        self._save(generate_pdf=True)

    def refresh(self) -> None:
        self.load_suppliers()
        self.search_products()
        self._valid = True


class ManualProductDialog(tk.Toplevel):
    def __init__(self, parent, database: Database, supplier_id: int):
        super().__init__(parent)
        self.database = database
        self.supplier_id = supplier_id
        self.product_id: int | None = None
        self.title("Article hors catalogue")
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        fields = [
            ("Référence fournisseur", "reference"),
            ("Désignation", "designation"),
            ("Unités par carton", "pack"),
            ("Prix unitaire HT", "price"),
            ("TVA (%)", "vat"),
        ]
        self.vars = {key: tk.StringVar() for _, key in fields}
        self.vars["pack"].set("1")
        self.vars["vat"].set("20")
        for row, (label, key) in enumerate(fields):
            ttk.Label(frame, text=label).grid(
                row=row, column=0, sticky="w", pady=5
            )
            ttk.Entry(frame, textvariable=self.vars[key], width=42).grid(
                row=row, column=1, sticky="ew", padx=(10, 0), pady=5
            )
        buttons = ttk.Frame(frame)
        buttons.grid(row=len(fields), column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Annuler", command=self.destroy).pack(
            side="left"
        )
        ttk.Button(
            buttons,
            text="Créer",
            style="Accent.TButton",
            command=self.save,
        ).pack(side="left", padx=(7, 0))

    def save(self) -> None:
        try:
            designation = self.vars["designation"].get().strip()
            if not designation:
                raise ValueError("La désignation est obligatoire.")
            pack = float(self.vars["pack"].get().replace(",", "."))
            price = float(self.vars["price"].get().replace(",", "."))
            vat = float(self.vars["vat"].get().replace(",", "."))
            self.product_id = self.database.create_manual_product(
                self.supplier_id,
                self.vars["reference"].get(),
                designation,
                pack,
                price,
                vat,
            )
            self.destroy()
        except ValueError as exc:
            messagebox.showerror("Article", str(exc), parent=self)


class OrdersPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header(
            "Historique des commandes",
            "Les prix et conditionnements restent ceux utilisés lors de la commande.",
        )
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            frame,
            columns=("number", "date", "supplier", "status", "ht", "ttc"),
            show="headings",
        )
        for column, title, width in (
            ("number", "N° commande", 125),
            ("date", "Date", 90),
            ("supplier", "Fournisseur", 270),
            ("status", "Statut", 95),
            ("ht", "Total HT", 100),
            ("ttc", "Total TTC", 100),
        ):
            self.tree.heading(column, text=title)
            self.tree.column(
                column,
                width=width,
                stretch=column == "supplier",
                anchor="w" if column == "supplier" else "center",
            )
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda event: self.edit_draft())
        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(
            actions,
            text="Modifier le brouillon",
            style="Accent.TButton",
            command=self.edit_draft,
        ).pack(side="left")
        ttk.Button(
            actions, text="Regénérer le PDF", command=self.regenerate_pdf
        ).pack(side="right")
        ttk.Button(
            actions, text="Ouvrir le PDF", command=self.open_pdf
        ).pack(side="right", padx=8)

    def selected_order(self):
        selected = self.tree.selection()
        return int(selected[0]) if selected else None

    def edit_draft(self) -> None:
        order_id = self.selected_order()
        if not order_id:
            return
        order, _ = self.database.get_order(order_id)
        if order["status"] != "Brouillon":
            messagebox.showinfo(
                "Modification",
                "Cette commande a déjà été générée. Seuls les brouillons "
                "peuvent être modifiés.",
                parent=self,
            )
            return
        self.app.show_page("new_order")
        order_page: OrderPage = self.app.pages["new_order"]  # type: ignore[assignment]
        order_page.load_order(order_id)

    def open_pdf(self) -> None:
        order_id = self.selected_order()
        if not order_id:
            return
        order, _ = self.database.get_order(order_id)
        if order["pdf_path"] and Path(order["pdf_path"]).is_file():
            open_path(order["pdf_path"])
        else:
            messagebox.showinfo(
                "PDF", "Aucun PDF n'a encore été généré.", parent=self
            )

    def regenerate_pdf(self) -> None:
        order_id = self.selected_order()
        if not order_id:
            return
        order, _ = self.database.get_order(order_id)
        output = choose_pdf_path(self, self.database, order)
        if output is None:
            return
        generate_order_pdf(self.database, order_id, output)
        self.refresh()
        messagebox.showinfo("PDF", f"PDF généré :\n{output}", parent=self)

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for order in self.database.list_orders():
            order_date = datetime.fromisoformat(order["order_date"]).strftime(
                "%d/%m/%Y"
            )
            self.tree.insert(
                "",
                "end",
                iid=str(order["id"]),
                values=(
                    order["order_number"],
                    order_date,
                    order["supplier_name"],
                    order["status"],
                    format_price(order["total_ht"], 2),
                    format_price(order["total_ttc"], 2),
                ),
            )
        self._valid = True


class SuppliersPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header(
            "Fournisseurs",
            "Numéro client, adresse de commande et seuil de franco.",
        )
        pane = ttk.Panedwindow(self, orient="horizontal")
        pane.pack(fill="both", expand=True)
        left = ttk.Frame(pane, style="Surface.TFrame", padding=12)
        right = ttk.Frame(pane, style="Surface.TFrame", padding=18)
        pane.add(left, weight=1)
        pane.add(right, weight=2)

        self.search_var = tk.StringVar()
        search = ttk.Entry(left, textvariable=self.search_var)
        search.pack(fill="x", pady=(0, 8))
        search.bind("<KeyRelease>", lambda event: self.filter_suppliers())
        self.tree = ttk.Treeview(
            left,
            columns=("name",),
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("name", text="Fournisseur")
        self.tree.column("name", width=260, stretch=True)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda event: self.load_selected())

        self.fields: dict[str, tk.StringVar] = {}
        field_defs = [
            ("Numéro client", "customer_number"),
            ("E-mail de commande", "email"),
            ("Téléphone", "phone"),
            ("Franco HT", "franco_ht"),
        ]
        ttk.Label(
            right,
            text="Configuration du fournisseur",
            style="Surface.TLabel",
            font=("Segoe UI Semibold", 12),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        for row, (label, key) in enumerate(field_defs, start=1):
            ttk.Label(right, text=label, style="Surface.TLabel").grid(
                row=row, column=0, sticky="w", pady=6
            )
            variable = tk.StringVar()
            ttk.Entry(right, textvariable=variable, width=48).grid(
                row=row, column=1, sticky="ew", padx=(12, 0), pady=6
            )
            self.fields[key] = variable
        ttk.Label(right, text="Notes", style="Surface.TLabel").grid(
            row=5, column=0, sticky="nw", pady=6
        )
        self.notes = tk.Text(
            right,
            width=46,
            height=7,
            font=("Segoe UI", 9),
            wrap="word",
            relief="solid",
            bd=1,
        )
        self.notes.grid(row=5, column=1, sticky="nsew", padx=(12, 0), pady=6)
        right.columnconfigure(1, weight=1)
        right.rowconfigure(5, weight=1)
        ttk.Button(
            right,
            text="Enregistrer",
            style="Accent.TButton",
            command=self.save,
        ).grid(row=6, column=1, sticky="e", pady=(12, 0))
        self.all_suppliers = []

    def filter_suppliers(self) -> None:
        term = self.search_var.get().strip().lower()
        self.tree.delete(*self.tree.get_children())
        for supplier in self.all_suppliers:
            if not term or term in supplier["name"].lower():
                self.tree.insert(
                    "", "end", iid=str(supplier["id"]), values=(supplier["name"],)
                )

    def load_selected(self) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        supplier = self.database.get_supplier(int(selected[0]))
        for key, variable in self.fields.items():
            value = supplier[key]
            variable.set("" if value is None else str(value).replace(".", ","))
        self.notes.delete("1.0", "end")
        self.notes.insert("1.0", supplier["notes"] or "")

    def save(self) -> None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo(
                "Fournisseur", "Sélectionnez un fournisseur.", parent=self
            )
            return
        franco_text = self.fields["franco_ht"].get().strip().replace(",", ".")
        try:
            franco = float(franco_text) if franco_text else None
        except ValueError:
            messagebox.showerror(
                "Fournisseur", "Le franco doit être un nombre.", parent=self
            )
            return
        self.database.update_supplier(
            int(selected[0]),
            self.fields["customer_number"].get(),
            self.fields["email"].get(),
            self.fields["phone"].get(),
            franco,
            self.notes.get("1.0", "end").strip(),
        )
        messagebox.showinfo(
            "Fournisseur", "Configuration enregistrée.", parent=self
        )

    def refresh(self) -> None:
        self.all_suppliers = self.database.list_suppliers(used_only=True)
        self.filter_suppliers()
        self._valid = True


class ImportPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header(
            "Mise à jour CAHPP",
            "Importez le nouveau fichier Excel ; les changements sont historisés.",
        )
        box = tk.Frame(
            self,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=18,
            pady=18,
        )
        box.pack(fill="x")
        self.path_var = tk.StringVar()
        ttk.Entry(box, textvariable=self.path_var).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(box, text="Choisir le fichier", command=self.browse).pack(
            side="left", padx=8
        )
        self.import_button = ttk.Button(
            box,
            text="Importer",
            style="Accent.TButton",
            command=self.start_import,
        )
        self.import_button.pack(side="left")

        progress_box = ttk.Frame(self)
        progress_box.pack(fill="x", pady=(16, 0))
        self.progress = ttk.Progressbar(
            progress_box, mode="determinate", maximum=100
        )
        self.progress.pack(fill="x")
        self.status_label = ttk.Label(
            progress_box,
            text="Sélectionnez la base complète tarifaire.",
            style="Subtitle.TLabel",
        )
        self.status_label.pack(anchor="w", pady=(5, 0))

        ttk.Label(
            self, text="Historique des imports", font=("Segoe UI Semibold", 11)
        ).pack(anchor="w", pady=(22, 8))
        self.tree = ttk.Treeview(
            self,
            columns=("date", "file", "rows", "added", "updated", "missing"),
            show="headings",
            height=10,
        )
        for column, title, width in (
            ("date", "Date", 135),
            ("file", "Fichier", 320),
            ("rows", "Articles", 90),
            ("added", "Ajoutés", 75),
            ("updated", "Modifiés", 75),
            ("missing", "Disparus", 75),
        ):
            self.tree.heading(column, text=title)
            self.tree.column(
                column,
                width=width,
                stretch=column == "file",
                anchor="w" if column == "file" else "center",
            )
        self.tree.pack(fill="both", expand=True)
        self.messages: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None

    def browse(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Sélectionner la base CAHPP",
            filetypes=[("Classeur Excel", "*.xlsx"), ("Tous les fichiers", "*.*")],
        )
        if path:
            self.path_var.set(path)

    def start_import(self) -> None:
        path = Path(self.path_var.get())
        if not path.is_file():
            messagebox.showwarning(
                "Import", "Sélectionnez un fichier Excel valide.", parent=self
            )
            return
        self.import_button.configure(state="disabled")
        self.progress["value"] = 0
        self.worker = threading.Thread(
            target=self._run_import, args=(path,), daemon=True
        )
        self.worker.start()
        self.after(100, self._poll_messages)

    def _run_import(self, path: Path) -> None:
        try:
            importer = CatalogImporter(self.database)
            result = importer.import_file(
                path,
                progress=lambda current, total, message: self.messages.put(
                    ("progress", current, message)
                ),
            )
            self.messages.put(("done", result))
        except Exception as exc:
            self.messages.put(("error", str(exc)))

    def _poll_messages(self) -> None:
        try:
            while True:
                message = self.messages.get_nowait()
                if message[0] == "progress":
                    self.progress["value"] = message[1]
                    self.status_label.configure(text=message[2])
                elif message[0] == "done":
                    self._import_done(message[1])
                    return
                elif message[0] == "error":
                    self.import_button.configure(state="normal")
                    self.status_label.configure(text="Échec de l'import.")
                    messagebox.showerror("Import CAHPP", message[1], parent=self)
                    return
        except queue.Empty:
            pass
        if self.worker and self.worker.is_alive():
            self.after(100, self._poll_messages)

    def _import_done(self, result: ImportResult) -> None:
        self.import_button.configure(state="normal")
        self.progress["value"] = 100
        if result.already_imported:
            self.status_label.configure(
                text="Ce fichier avait déjà été importé."
            )
            messagebox.showinfo(
                "Import CAHPP",
                "Ce fichier est identique à un catalogue déjà importé.",
                parent=self,
            )
        else:
            self.status_label.configure(text="Catalogue mis à jour.")
            details = (
                f"{result.row_count:,} articles lus\n"
                f"{result.added_count:,} ajoutés\n"
                f"{result.updated_count:,} modifiés\n"
                f"{result.missing_count:,} absents du nouveau fichier"
            ).replace(",", " ")
            messagebox.showinfo("Import CAHPP terminé", details, parent=self)
        self.app.refresh_pages()
        self.refresh()

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for item in self.database.latest_imports():
            imported = datetime.fromisoformat(item["imported_at"]).strftime(
                "%d/%m/%Y %H:%M"
            )
            self.tree.insert(
                "",
                "end",
                iid=str(item["id"]),
                values=(
                    imported,
                    item["filename"],
                    format_number(item["row_count"]),
                    format_number(item["added_count"]),
                    format_number(item["updated_count"]),
                    format_number(item["missing_count"]),
                ),
            )
        self._valid = True


class SettingsPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header(
            "Paramètres",
            "Identité utilisée sur les bons de commande.",
        )
        surface = ttk.Frame(self, style="Surface.TFrame", padding=18)
        surface.pack(fill="both", expand=True)
        fields = [
            ("Nom de l'établissement", "establishment_name"),
            ("Sous-titre / service", "establishment_subtitle"),
            ("Adresse - ligne 1", "address_line1"),
            ("Adresse - ligne 2", "address_line2"),
            ("Code postal et ville", "postal_city"),
            ("Téléphone", "phone"),
            ("E-mail", "email"),
            ("FINESS", "finess"),
            ("SIRET", "siret"),
            ("Code APE", "ape"),
            ("Titre du document PDF", "pdf_title"),
            ("Texte du pied de page PDF", "pdf_footer_text"),
        ]
        self.vars = {key: tk.StringVar() for _, key in fields}
        for row, (label, key) in enumerate(fields):
            ttk.Label(surface, text=label, style="Surface.TLabel").grid(
                row=row, column=0, sticky="w", pady=5
            )
            ttk.Entry(
                surface, textvariable=self.vars[key], width=70
            ).grid(row=row, column=1, sticky="ew", padx=(14, 0), pady=5)
        row = len(fields)
        ttk.Label(surface, text="Logo", style="Surface.TLabel").grid(
            row=row, column=0, sticky="w", pady=5
        )
        self.logo_var = tk.StringVar()
        logo_row = ttk.Frame(surface, style="Surface.TFrame")
        logo_row.grid(row=row, column=1, sticky="ew", padx=(14, 0), pady=5)
        ttk.Entry(logo_row, textvariable=self.logo_var).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(logo_row, text="Parcourir", command=self.browse_logo).pack(
            side="left", padx=(7, 0)
        )
        row += 1
        ttk.Label(
            surface,
            text="Dossier PDF par défaut",
            style="Surface.TLabel",
        ).grid(row=row, column=0, sticky="w", pady=5)
        self.pdf_directory_var = tk.StringVar()
        pdf_directory_row = ttk.Frame(surface, style="Surface.TFrame")
        pdf_directory_row.grid(
            row=row, column=1, sticky="ew", padx=(14, 0), pady=5
        )
        ttk.Entry(
            pdf_directory_row, textvariable=self.pdf_directory_var
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(
            pdf_directory_row,
            text="Parcourir",
            command=self.browse_pdf_directory,
        ).pack(side="left", padx=(7, 0))
        row += 1
        self.show_page_number_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            surface,
            text="Afficher le numéro de page sur le PDF",
            variable=self.show_page_number_var,
        ).grid(row=row, column=1, sticky="w", padx=(14, 0), pady=5)
        ttk.Button(
            surface,
            text="Enregistrer",
            style="Accent.TButton",
            command=self.save,
        ).grid(row=row + 1, column=1, sticky="e", pady=(16, 0))
        ttk.Button(
            surface,
            text="Créer une sauvegarde",
            command=self.backup,
        ).grid(row=row + 1, column=0, sticky="w", pady=(16, 0))
        surface.columnconfigure(1, weight=1)

    def browse_logo(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Sélectionner le logo",
            filetypes=[
                ("Images", "*.png;*.jpg;*.jpeg"),
                ("Tous les fichiers", "*.*"),
            ],
        )
        if path:
            self.logo_var.set(path)

    def browse_pdf_directory(self) -> None:
        current = self.pdf_directory_var.get().strip()
        initial = current if current and Path(current).is_dir() else str(EXPORT_DIR)
        path = filedialog.askdirectory(
            parent=self,
            title="Choisir le dossier PDF par défaut",
            initialdir=initial,
        )
        if path:
            self.pdf_directory_var.set(path)

    def save(self) -> None:
        values = {key: variable.get() for key, variable in self.vars.items()}
        values["logo_path"] = self.logo_var.get()
        values["pdf_default_directory"] = self.pdf_directory_var.get()
        values["pdf_show_page_number"] = (
            "1" if self.show_page_number_var.get() else "0"
        )
        self.database.save_settings(values)
        messagebox.showinfo(
            "Paramètres", "Les paramètres ont été enregistrés.", parent=self
        )

    def backup(self) -> None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        destination = BACKUP_DIR / f"commandes-cahpp-{timestamp}.sqlite3"
        self.database.backup(destination)
        messagebox.showinfo(
            "Sauvegarde",
            f"La sauvegarde a été créée :\n{destination}",
            parent=self,
        )

    def refresh(self) -> None:
        settings = self.database.get_settings()
        for key, variable in self.vars.items():
            variable.set(settings.get(key, ""))
        self.logo_var.set(settings.get("logo_path", ""))
        self.pdf_directory_var.set(
            settings.get("pdf_default_directory", "")
        )
        self.show_page_number_var.set(
            settings.get("pdf_show_page_number", "1") != "0"
        )
        self._valid = True
