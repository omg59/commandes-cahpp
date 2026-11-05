from __future__ import annotations

from datetime import date
from tkinter import ttk
from .base import BasePage
from .components import TreeviewSorter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .order import OrderPage


class SuggestionsPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header(
            "Articles à recommander",
            "Suggestions calculées à partir du rythme réel des commandes précédentes.",
        )
        info = ttk.Frame(self)
        info.pack(fill="x", pady=(0, 10))
        ttk.Label(
            info,
            text=(
                "Une suggestion apparaît après au moins deux intervalles "
                "exploitables. Elle ne crée jamais de commande automatiquement."
            ),
            style="Subtitle.TLabel",
        ).pack(side="left")
        ttk.Button(
            info, text="Actualiser", style="Accent.TButton", command=self.refresh
        ).pack(side="right")
        self.tree = ttk.Treeview(
            self,
            columns=(
                "supplier",
                "reference",
                "designation",
                "last",
                "frequency",
                "due",
            ),
            show="headings",
            selectmode="browse",
        )
        headings = {
            "supplier": "Fournisseur",
            "reference": "Référence",
            "designation": "Désignation",
            "last": "Dernière commande",
            "frequency": "Rythme moyen",
            "due": "Échéance estimée",
        }
        for column, width, anchor in (
            ("supplier", 180, "w"),
            ("reference", 120, "center"),
            ("designation", 470, "w"),
            ("last", 130, "center"),
            ("frequency", 120, "center"),
            ("due", 130, "center"),
        ):
            self.tree.heading(column, text=headings[column])
            self.tree.column(
                column,
                width=width,
                anchor=anchor,
                stretch=column == "designation",
            )
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda event: self.start_order())
        self.sorter = TreeviewSorter(
            self.tree,
            headings,
            numeric_columns={"frequency", "due"},
        )
        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(10, 0))
        self.result_label = ttk.Label(actions, text="", style="Subtitle.TLabel")
        self.result_label.pack(side="left")
        ttk.Button(
            actions,
            text="Commander cet article",
            style="Accent.TButton",
            command=self.start_order,
        ).pack(side="right")

    def start_order(self) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        product_id = int(selected[0])
        self.app.show_page("new_order")
        page: OrderPage = self.app.pages["new_order"]  # type: ignore[assignment]
        page.start_with_product(product_id)

    def refresh(self) -> None:
        rows = self.database.reorder_suggestions()
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            overdue = int(row["overdue_days"] or 0)
            due_text = (
                f"En retard de {overdue} j" if overdue > 0 else "À prévoir maintenant"
            )
            try:
                last_date = date.fromisoformat(row["last_order_date"])
                last_text = last_date.strftime("%d/%m/%Y")
            except (TypeError, ValueError):
                last_text = row["last_order_date"] or "—"
            self.tree.insert(
                "",
                "end",
                iid=str(row["product_id"]),
                values=(
                    row["supplier_name"],
                    row["supplier_ref"] or "—",
                    row["designation"],
                    last_text,
                    f"{int(row['average_interval_days'] or 0)} j",
                    due_text,
                ),
            )
        self.result_label.configure(text=f"{len(rows)} suggestion(s)")
        self.sorter.reapply()
        self._valid = True
