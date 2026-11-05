from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from .base import BasePage
from .components import FeedbackButton
from .common import supplier_field_display_value
from ..numbers import parse_decimal


class SuppliersPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._supplier_baseline: dict[str, object] | None = None
        self._loaded_supplier_id: int | None = None
        self._restoring_selection = False
        self.header(
            "Fournisseurs",
            "Coordonnées, destinataire des commandes et seuils commerciaux.",
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
            ("Contact", "contact_name"),
            ("E-mail de commande", "email"),
            ("Téléphone", "phone"),
            ("Adresse", "address"),
            ("Site web", "website"),
            ("Minimum de commande HT", "minimum_order_ht"),
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
        notes_row = len(field_defs) + 1
        ttk.Label(right, text="Notes", style="Surface.TLabel").grid(
            row=notes_row, column=0, sticky="nw", pady=6
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
        self.notes.grid(row=notes_row, column=1, sticky="nsew", padx=(12, 0), pady=6)
        right.columnconfigure(1, weight=1)
        right.rowconfigure(notes_row, weight=1)
        self.save_button = FeedbackButton(
            right,
            text="Enregistrer",
            command=self.save,
            success_text="✓ Fournisseur enregistré",
        )
        self.save_button.grid(row=notes_row + 1, column=1, sticky="e", pady=(12, 0))
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
        if self._restoring_selection:
            return
        selected = self.tree.selection()
        if not selected:
            return
        supplier_id = int(selected[0])
        if (
            self._loaded_supplier_id is not None
            and supplier_id != self._loaded_supplier_id
            and self.has_unsaved_changes()
        ):
            discard = messagebox.askyesno(
                "Modifications non enregistrées",
                (
                    "Abandonner les modifications en cours et ouvrir "
                    "un autre fournisseur ?"
                ),
                icon="warning",
                parent=self,
            )
            if not discard:
                self._restoring_selection = True
                self.tree.selection_set(str(self._loaded_supplier_id))
                self.tree.see(str(self._loaded_supplier_id))
                self._restoring_selection = False
                return
        supplier = self.database.get_supplier(supplier_id)
        if supplier is None:
            return
        self._loaded_supplier_id = supplier_id
        for key, variable in self.fields.items():
            variable.set(supplier_field_display_value(key, supplier[key]))
        self.notes.delete("1.0", "end")
        self.notes.insert("1.0", supplier["notes"] or "")
        self._supplier_baseline = self._current_supplier_values()

    def _current_supplier_values(self) -> dict[str, object]:
        values: dict[str, object] = {
            key: variable.get() for key, variable in self.fields.items()
        }
        values["notes"] = self.notes.get("1.0", "end").strip()
        values["supplier_id"] = self._loaded_supplier_id
        return values

    def has_unsaved_changes(self) -> bool:
        return (
            self._supplier_baseline is not None
            and self._current_supplier_values() != self._supplier_baseline
        )

    def save(self) -> bool:
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo(
                "Fournisseur", "Sélectionnez un fournisseur.", parent=self
            )
            return False
        franco_text = self.fields["franco_ht"].get().strip().replace(",", ".")
        minimum_text = self.fields["minimum_order_ht"].get().strip().replace(",", ".")
        try:
            franco = (
                float(parse_decimal(franco_text, "Franco HT", minimum=0))
                if franco_text
                else None
            )
            minimum = (
                float(parse_decimal(minimum_text, "Minimum HT", minimum=0))
                if minimum_text
                else None
            )
        except ValueError:
            messagebox.showerror(
                "Fournisseur",
                "Le minimum et le franco doivent être des nombres.",
                parent=self,
            )
            return False
        self.database.update_supplier(
            int(selected[0]),
            self.fields["customer_number"].get(),
            self.fields["email"].get(),
            self.fields["phone"].get(),
            franco,
            self.notes.get("1.0", "end").strip(),
            contact_name=self.fields["contact_name"].get(),
            address=self.fields["address"].get(),
            website=self.fields["website"].get(),
            minimum_order_ht=minimum,
        )
        self._supplier_baseline = self._current_supplier_values()
        self.app.sync_team_data()
        return True

    def refresh(self) -> None:
        if self.has_unsaved_changes():
            self._valid = True
            return
        selected_id = self._loaded_supplier_id
        self.all_suppliers = self.database.list_suppliers(used_only=True)
        self.filter_suppliers()
        if selected_id is not None and self.tree.exists(str(selected_id)):
            self.tree.selection_set(str(selected_id))
            self.tree.see(str(selected_id))
            self.load_selected()
        self._valid = True
