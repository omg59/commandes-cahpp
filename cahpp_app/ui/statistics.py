from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, ttk
from ..statistics_export import export_statistics_workbook
from .base import BasePage
from .common import COLORS
from .components import TreeviewSorter
from .common import format_number
from .common import format_price
from .common import months_before
from .common import open_path


class StatisticsPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header(
            "Statistiques",
            "Analyse des commandes envoyées par période, fournisseur et produit.",
        )
        filters = ttk.Frame(self)
        filters.pack(fill="x", pady=(0, 12))
        ttk.Label(filters, text="Période").pack(side="left")
        self.period_var = tk.StringVar(value="Cette année")
        period_box = ttk.Combobox(
            filters,
            textvariable=self.period_var,
            state="readonly",
            values=(
                "Cette année",
                "12 derniers mois",
                "Tout l'historique",
                "Personnalisée",
            ),
            width=20,
        )
        period_box.pack(side="left", padx=(7, 16))
        period_box.bind("<<ComboboxSelected>>", self.apply_period)
        ttk.Label(filters, text="Du").pack(side="left")
        self.date_from_var = tk.StringVar()
        ttk.Entry(filters, textvariable=self.date_from_var, width=13).pack(
            side="left", padx=6
        )
        ttk.Label(filters, text="au").pack(side="left")
        self.date_to_var = tk.StringVar()
        ttk.Entry(filters, textvariable=self.date_to_var, width=13).pack(
            side="left", padx=6
        )
        ttk.Button(
            filters, text="Actualiser", style="Accent.TButton", command=self.refresh
        ).pack(side="left", padx=8)
        ttk.Button(filters, text="Exporter Excel…", command=self.export_excel).pack(
            side="left"
        )
        self.period_status = ttk.Label(filters, text="", style="Subtitle.TLabel")
        self.period_status.pack(side="right")

        self.cards = ttk.Frame(self)
        self.cards.pack(fill="x", pady=(0, 14))
        self.card_values: dict[str, tk.Label] = {}
        for index, (key, label) in enumerate(
            (
                ("order_count", "Commandes envoyées"),
                ("supplier_count", "Fournisseurs"),
                ("total_ht", "Total HT"),
                ("total_ttc", "Total TTC"),
            )
        ):
            card = tk.Frame(
                self.cards,
                bg=COLORS["surface"],
                highlightbackground=COLORS["border"],
                highlightthickness=1,
                padx=16,
                pady=12,
            )
            card.grid(row=0, column=index, sticky="ew", padx=(0, 12))
            self.cards.columnconfigure(index, weight=1)
            value = tk.Label(
                card,
                text="0",
                bg=COLORS["surface"],
                fg=COLORS["accent"],
                font=("Segoe UI Semibold", 18),
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

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)
        supplier_tab = ttk.Frame(notebook, padding=8)
        product_tab = ttk.Frame(notebook, padding=8)
        prices_tab = ttk.Frame(notebook, padding=8)
        notebook.add(supplier_tab, text="Par fournisseur")
        notebook.add(product_tab, text="Par produit")
        notebook.add(prices_tab, text="Écarts de prix")

        supplier_frame = ttk.Frame(supplier_tab)
        supplier_frame.pack(fill="both", expand=True)
        self.supplier_tree = ttk.Treeview(
            supplier_frame,
            columns=(
                "supplier",
                "orders",
                "ht",
                "ttc",
                "confirm",
                "delivery",
                "waiting",
            ),
            show="headings",
        )
        supplier_headings = {
            "supplier": "Fournisseur",
            "orders": "Commandes",
            "ht": "Total HT",
            "ttc": "Total TTC",
            "confirm": "Confirmation moy.",
            "delivery": "Livraison moy.",
            "waiting": "À recevoir",
        }
        for column, width, anchor in (
            ("supplier", 330, "w"),
            ("orders", 90, "center"),
            ("ht", 115, "e"),
            ("ttc", 115, "e"),
            ("confirm", 115, "center"),
            ("delivery", 115, "center"),
            ("waiting", 90, "center"),
        ):
            self.supplier_tree.heading(column, text=supplier_headings[column])
            self.supplier_tree.column(
                column,
                width=width,
                anchor=anchor,
                stretch=column == "supplier",
            )
        supplier_scrollbar = ttk.Scrollbar(
            supplier_frame,
            orient="vertical",
            command=self.supplier_tree.yview,
        )
        self.supplier_tree.configure(yscrollcommand=supplier_scrollbar.set)
        self.supplier_tree.pack(side="left", fill="both", expand=True)
        supplier_scrollbar.pack(side="right", fill="y")
        self.supplier_sorter = TreeviewSorter(
            self.supplier_tree,
            supplier_headings,
            numeric_columns={"orders", "ht", "ttc", "confirm", "delivery", "waiting"},
        )

        product_frame = ttk.Frame(product_tab)
        product_frame.pack(fill="both", expand=True)
        self.product_tree = ttk.Treeview(
            product_frame,
            columns=("supplier", "reference", "designation", "cartons", "units", "ht"),
            show="headings",
        )
        product_headings = {
            "supplier": "Fournisseur",
            "reference": "Référence",
            "designation": "Désignation",
            "cartons": "Cartons",
            "units": "Unités",
            "ht": "Total HT",
        }
        for column, width, anchor in (
            ("supplier", 170, "w"),
            ("reference", 110, "center"),
            ("designation", 460, "w"),
            ("cartons", 90, "center"),
            ("units", 90, "center"),
            ("ht", 120, "e"),
        ):
            self.product_tree.heading(column, text=product_headings[column])
            self.product_tree.column(
                column,
                width=width,
                anchor=anchor,
                stretch=column == "designation",
            )
        scrollbar = ttk.Scrollbar(
            product_frame, orient="vertical", command=self.product_tree.yview
        )
        self.product_tree.configure(yscrollcommand=scrollbar.set)
        self.product_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.product_sorter = TreeviewSorter(
            self.product_tree,
            product_headings,
            numeric_columns={"cartons", "units", "ht"},
        )

        prices_frame = ttk.Frame(prices_tab)
        prices_frame.pack(fill="both", expand=True)
        self.prices_tree = ttk.Treeview(
            prices_frame,
            columns=(
                "supplier",
                "reference",
                "designation",
                "order",
                "old",
                "current",
                "difference",
            ),
            show="headings",
        )
        price_headings = {
            "supplier": "Fournisseur",
            "reference": "Référence",
            "designation": "Désignation",
            "order": "Dernière commande",
            "old": "PU commandé",
            "current": "PU actuel",
            "difference": "Écart",
        }
        for column, width, anchor in (
            ("supplier", 170, "w"),
            ("reference", 110, "center"),
            ("designation", 400, "w"),
            ("order", 135, "center"),
            ("old", 105, "e"),
            ("current", 105, "e"),
            ("difference", 105, "e"),
        ):
            self.prices_tree.heading(column, text=price_headings[column])
            self.prices_tree.column(
                column,
                width=width,
                anchor=anchor,
                stretch=column == "designation",
            )
        prices_scrollbar = ttk.Scrollbar(
            prices_frame, orient="vertical", command=self.prices_tree.yview
        )
        self.prices_tree.configure(yscrollcommand=prices_scrollbar.set)
        self.prices_tree.pack(side="left", fill="both", expand=True)
        prices_scrollbar.pack(side="right", fill="y")
        self.prices_sorter = TreeviewSorter(
            self.prices_tree,
            price_headings,
            numeric_columns={"old", "current", "difference"},
        )
        self._last_result: dict[str, object] | None = None
        self._last_period: tuple[date, date] | None = None
        self.apply_period()

    def apply_period(self, event=None) -> None:
        today = date.today()
        period = self.period_var.get()
        if period == "Cette année":
            start = date(today.year, 1, 1)
        elif period == "12 derniers mois":
            start = months_before(today, 12)
        elif period == "Tout l'historique":
            start = date(2000, 1, 1)
        else:
            return
        self.date_from_var.set(start.isoformat())
        self.date_to_var.set(today.isoformat())
        if self.winfo_exists():
            self.refresh()

    def refresh(self) -> None:
        try:
            date_from = date.fromisoformat(self.date_from_var.get().strip())
            date_to = date.fromisoformat(self.date_to_var.get().strip())
            if date_from > date_to:
                raise ValueError
        except ValueError:
            self.period_status.configure(
                text="Dates attendues : AAAA-MM-JJ", foreground=COLORS["danger"]
            )
            self._valid = True
            return
        result = self.database.statistics(date_from, date_to)
        self._last_result = result
        self._last_period = (date_from, date_to)
        summary = dict(result.get("summary") or {})
        self.card_values["order_count"].configure(
            text=format_number(summary.get("order_count", 0))
        )
        self.card_values["supplier_count"].configure(
            text=format_number(summary.get("supplier_count", 0))
        )
        self.card_values["total_ht"].configure(
            text=format_price(summary.get("total_ht", 0), 2)
        )
        self.card_values["total_ttc"].configure(
            text=format_price(summary.get("total_ttc", 0), 2)
        )
        self.supplier_tree.delete(*self.supplier_tree.get_children())
        for index, row in enumerate(result.get("suppliers", [])):
            self.supplier_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    row["supplier_name"],
                    format_number(row["order_count"]),
                    format_price(row["total_ht"], 2),
                    format_price(row["total_ttc"], 2),
                    (
                        f"{format_number(row['average_confirmation_days'], 1)} j"
                        if row["average_confirmation_days"] is not None
                        else "—"
                    ),
                    (
                        f"{format_number(row['average_delivery_days'], 1)} j"
                        if row["average_delivery_days"] is not None
                        else "—"
                    ),
                    format_number(row["incomplete_count"]),
                ),
            )
        self.product_tree.delete(*self.product_tree.get_children())
        for index, row in enumerate(result.get("products", [])):
            self.product_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    row["supplier_name"],
                    row["supplier_ref"] or "—",
                    row["designation"],
                    format_number(row["cartons"], 2),
                    format_number(row["total_units"], 2),
                    format_price(row["total_ht"], 2),
                ),
            )
        self.period_status.configure(
            text=f"Du {date_from:%d/%m/%Y} au {date_to:%d/%m/%Y}",
            foreground=COLORS["muted"],
        )
        self.prices_tree.delete(*self.prices_tree.get_children())
        for index, row in enumerate(result.get("price_variances", [])):
            self.prices_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    row["supplier_name"],
                    row["supplier_ref"] or "—",
                    row["designation"],
                    row["order_number"],
                    format_price(row["ordered_price"]),
                    format_price(row["current_price"]),
                    f"{format_price(row['difference'])} ({format_number(row['difference_percent'], 1)} %)",
                ),
            )
        self._valid = True

    def export_excel(self) -> None:
        self.refresh()
        if not self._last_result or not self._last_period:
            return
        destination = filedialog.asksaveasfilename(
            parent=self,
            title="Exporter les statistiques",
            initialfile=(
                f"Statistiques-commandes-{self._last_period[0].isoformat()}-"
                f"{self._last_period[1].isoformat()}.xlsx"
            ),
            defaultextension=".xlsx",
            filetypes=[("Classeur Excel", "*.xlsx")],
        )
        if not destination:
            return
        try:
            path = export_statistics_workbook(
                self._last_result,
                self._last_period[0],
                self._last_period[1],
                destination,
            )
        except OSError as exc:
            messagebox.showerror("Export Excel", str(exc), parent=self)
            return
        open_path(path.parent)
