from __future__ import annotations

from ..numbers import parse_decimal

import tkinter as tk
import json
from datetime import date
from decimal import Decimal
from tkinter import messagebox, simpledialog, ttk
from ..collaboration import CollaborationError, ResourceLock
from ..database import Database
from ..pdf_export import generate_order_pdf
from .base import BasePage
from .common import COLORS
from .components import FeedbackButton
from .components import TreeviewColumnSizer
from .components import TreeviewSorter
from .common import choose_pdf_path
from .common import filter_supplier_names
from .common import format_number
from .common import format_pack
from .common import format_price
from .common import fractional_carton_lines
from .common import open_path
from .search import AsyncProductSearch


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
        self.supplier_box.bind("<Down>", self._move_supplier_suggestion)
        self.supplier_box.bind(
            "<Up>",
            lambda event: self._move_supplier_suggestion(event, -1),
        )
        self.supplier_box.bind(
            "<FocusOut>",
            lambda event: self.after(120, self._hide_supplier_suggestions_if_unused),
            add="+",
        )
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

        ttk.Label(left, text="Articles disponibles", style="Surface.TLabel").pack(
            anchor="w"
        )
        search_row = ttk.Frame(left, style="Surface.TFrame")
        search_row.pack(fill="x", pady=(8, 8))
        self.product_search_var = tk.StringVar()
        search_entry = ttk.Entry(search_row, textvariable=self.product_search_var)
        search_entry.pack(side="left", fill="x", expand=True)
        search_entry.bind("<KeyRelease>", self._schedule_search)
        ttk.Button(search_row, text="Chercher", command=self.search_products).pack(
            side="left", padx=(6, 0)
        )

        self.product_tree = ttk.Treeview(
            left,
            columns=("ref", "designation", "pack", "price"),
            show="headings",
            selectmode="browse",
            height=14,
        )
        product_headings = {
            "ref": "Référence",
            "designation": "Désignation",
            "pack": "Conditionnement",
            "price": "PU HT",
        }
        for column, title, width in (
            ("ref", "Référence", 90),
            ("designation", "Désignation", 260),
            ("pack", "Conditionnement", 120),
            ("price", "PU HT", 75),
        ):
            self.product_tree.heading(column, text=title)
            self.product_tree.column(
                column,
                width=width,
                stretch=column == "designation",
                anchor="w" if column == "designation" else "center",
            )
        self.product_sorter = TreeviewSorter(
            self.product_tree,
            product_headings,
            numeric_columns={"pack", "price"},
        )
        self.product_column_sizer = TreeviewColumnSizer(
            self.product_tree,
            {
                "ref": 90,
                "designation": 260,
                "pack": 120,
                "price": 75,
            },
            flexible_column="designation",
            minimum_widths={
                "ref": 72,
                "designation": 120,
                "pack": 90,
                "price": 65,
            },
        )
        self.product_tree.pack(fill="both", expand=True)
        self.product_status = ttk.Label(
            left, text="Choisissez un fournisseur.", style="Surface.TLabel"
        )
        self.product_status.pack(fill="x", pady=(4, 0))
        self.more_products = ttk.Button(
            left,
            text="Afficher 100 de plus",
            command=self._show_more_products,
            state="disabled",
        )
        self.more_products.pack(anchor="w", pady=(4, 0))
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

        ttk.Label(right, text="Contenu de la commande", style="Surface.TLabel").pack(
            anchor="w"
        )
        self.cart_tree = ttk.Treeview(
            right,
            columns=("designation", "ref", "cartons", "pack", "price", "total"),
            show="headings",
            selectmode="browse",
            height=15,
        )
        cart_headings = {
            "designation": "Désignation",
            "ref": "Réf.",
            "cartons": "Cartons",
            "pack": "Unités/carton",
            "price": "PU HT",
            "total": "Total HT",
        }
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
        self.cart_sorter = TreeviewSorter(
            self.cart_tree,
            cart_headings,
            numeric_columns={"cartons", "pack", "price", "total"},
        )
        self.cart_column_sizer = TreeviewColumnSizer(
            self.cart_tree,
            {
                "designation": 270,
                "ref": 90,
                "cartons": 65,
                "pack": 85,
                "price": 75,
                "total": 85,
            },
            flexible_column="designation",
            minimum_widths={
                "designation": 120,
                "ref": 65,
                "cartons": 58,
                "pack": 76,
                "price": 62,
                "total": 68,
            },
        )
        self.cart_tree.pack(fill="both", expand=True, pady=(8, 0))
        self.cart_tree.bind("<Double-1>", lambda event: self.edit_quantity())

        cart_buttons = ttk.Frame(right, style="Surface.TFrame")
        cart_buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(
            cart_buttons, text="Modifier la quantité", command=self.edit_quantity
        ).pack(side="left")
        ttk.Button(cart_buttons, text="Retirer", command=self.remove_line).pack(
            side="left", padx=6
        )
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
        ttk.Label(notes_frame, text="Service / unité").pack(side="left")
        self.requester_var = tk.StringVar()
        ttk.Entry(notes_frame, textvariable=self.requester_var, width=22).pack(
            side="left", padx=(8, 14)
        )
        ttk.Label(notes_frame, text="Note").pack(side="left")
        self.notes_var = tk.StringVar()
        ttk.Entry(notes_frame, textvariable=self.notes_var).pack(
            side="left", fill="x", expand=True, padx=8
        )
        self.save_draft_button = FeedbackButton(
            notes_frame,
            text="Enregistrer le brouillon",
            command=self.save_draft,
            success_text="✓ Brouillon enregistré",
        )
        self.save_draft_button.pack(side="right")
        self.generate_button = FeedbackButton(
            notes_frame,
            text="Générer la commande",
            command=self.save_and_generate,
            success_text="✓ Commande générée",
        )
        self.generate_button.pack(side="right", padx=(0, 8))

        self.supplier_suggestions = tk.Listbox(
            self,
            activestyle="dotbox",
            exportselection=False,
            font=("Segoe UI", 9),
            bg="white",
            fg=COLORS["text"],
            selectbackground=COLORS["accent"],
            selectforeground="white",
            relief="solid",
            borderwidth=1,
            highlightthickness=0,
        )
        self.supplier_suggestions.bind(
            "<ButtonRelease-1>",
            self._choose_supplier_suggestion,
        )
        self._supplier_matches: list[str] = []
        self.supplier_map: dict[str, int] = {}
        self._all_supplier_names: list[str] = []
        self.cart: list[dict[str, object]] = []
        self._search_after = None
        self._previous_supplier = ""
        self.current_order_id: int | None = None
        self.current_order_date: date | None = None
        self.current_order_lock: ResourceLock | None = None
        self._product_limit = 100
        self._product_render_after = None
        self._product_rows = []
        self._product_position = 0
        self._products_have_more = False
        self._product_search = AsyncProductSearch(
            self, self.database, self._products_loaded
        )
        self._editor_baseline = self._editor_state()

    def _editor_state(self):
        return (
            self.supplier_var.get(),
            self.notes_var.get(),
            self.requester_var.get(),
            json.dumps(self.cart, sort_keys=True, default=str),
        )

    def has_unsaved_changes(self) -> bool:
        return self._editor_state() != self._editor_baseline

    def _cancel_product_load(self):
        self._product_search.invalidate()
        if self._product_render_after:
            self.after_cancel(self._product_render_after)
            self._product_render_after = None
        self._product_rows = []
        self.more_products.configure(state="disabled")

    def _schedule_search(self, event=None) -> None:
        self._cancel_product_load()
        if self._search_after:
            self.after_cancel(self._search_after)
        query = self.product_search_var.get().strip()
        if query and len(query) < 2:
            self._search_after = None
            self.product_status.configure(text="Saisissez au moins 2 caractères.")
            return
        self._search_after = self.after(350, self.search_products)

    def load_suppliers(self) -> None:
        suppliers = self.database.list_suppliers(used_only=True)
        self.supplier_map = {row["name"]: row["id"] for row in suppliers}
        self._all_supplier_names = list(self.supplier_map)
        self.supplier_box["values"] = self._all_supplier_names
        if self.supplier_var.get() not in self.supplier_map:
            self.supplier_var.set("")

    def _filter_suppliers(self, event=None) -> None:
        if event and event.keysym in {"Escape", "Tab"}:
            self._hide_supplier_suggestions()
            return
        if event and event.keysym in {
            "Up",
            "Down",
            "Left",
            "Right",
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
            else:
                self._accept_selected_supplier()
            self._hide_supplier_suggestions()
            return
        if self.supplier_var.get().strip() and matches:
            self._show_supplier_suggestions(matches)
        else:
            self._hide_supplier_suggestions()

    def _show_supplier_suggestions(self, matches: list[str]) -> None:
        self._supplier_matches = matches
        self.supplier_suggestions.delete(0, tk.END)
        for name in matches:
            self.supplier_suggestions.insert(tk.END, name)
        rows = min(9, len(matches))
        self.supplier_suggestions.configure(height=rows)
        self.update_idletasks()
        x = self.supplier_box.winfo_rootx() - self.winfo_rootx()
        y = (
            self.supplier_box.winfo_rooty()
            - self.winfo_rooty()
            + self.supplier_box.winfo_height()
        )
        width = max(220, self.supplier_box.winfo_width())
        row_height = max(20, self.supplier_box.winfo_height())
        self.supplier_suggestions.place(
            x=x,
            y=y,
            width=width,
            height=rows * row_height + 2,
        )
        self.supplier_suggestions.lift()
        self.supplier_suggestions.selection_clear(0, tk.END)
        self.supplier_suggestions.selection_set(0)
        self.supplier_suggestions.activate(0)

    def _hide_supplier_suggestions(self) -> None:
        self.supplier_suggestions.place_forget()
        self._supplier_matches = []

    def _hide_supplier_suggestions_if_unused(self) -> None:
        # La liste native d'un ttk.Combobox existe dans Tcl mais pas dans le
        # registre de widgets Python. focus_get() tente de la résoudre en
        # objet Python et peut lever KeyError ; le chemin Tcl suffit ici.
        try:
            focused = str(self.tk.call("focus"))
        except tk.TclError:
            return  # Fenêtre/interpréteur déjà fermé lors du callback différé.
        if focused not in (str(self.supplier_box), str(self.supplier_suggestions)):
            self._hide_supplier_suggestions()

    def _move_supplier_suggestion(self, event=None, direction: int = 1):
        if not self._supplier_matches:
            matches = filter_supplier_names(
                self._all_supplier_names,
                self.supplier_var.get(),
            )
            if matches:
                self._show_supplier_suggestions(matches)
        if not self._supplier_matches:
            return "break"
        selected = self.supplier_suggestions.curselection()
        current = selected[0] if selected else (-1 if direction > 0 else 0)
        target = max(
            0,
            min(len(self._supplier_matches) - 1, current + direction),
        )
        self.supplier_suggestions.selection_clear(0, tk.END)
        self.supplier_suggestions.selection_set(target)
        self.supplier_suggestions.activate(target)
        self.supplier_suggestions.see(target)
        return "break"

    def _accept_selected_supplier(self) -> bool:
        selected = self.supplier_suggestions.curselection()
        if not selected or not self._supplier_matches:
            return False
        self.supplier_var.set(self._supplier_matches[selected[0]])
        self.supplier_changed()
        return True

    def _choose_supplier_suggestion(self, event=None) -> None:
        if event is not None:
            index = self.supplier_suggestions.nearest(event.y)
            self.supplier_suggestions.selection_clear(0, tk.END)
            self.supplier_suggestions.selection_set(index)
        self._accept_selected_supplier()
        self._hide_supplier_suggestions()
        self.supplier_box.focus_set()
        self.supplier_box.icursor(tk.END)

    def selected_supplier_id(self) -> int | None:
        return self.supplier_map.get(self.supplier_var.get())

    def _update_threshold_label(self, total: Decimal = Decimal("0")) -> None:
        supplier_id = self.selected_supplier_id()
        supplier = self.database.get_supplier(supplier_id) if supplier_id else None
        if supplier is None:
            self.franco_label.configure(text="", foreground=COLORS["muted"])
            return
        messages = []
        warning = False
        minimum = supplier["minimum_order_ht"]
        franco = supplier["franco_ht"]
        if minimum is not None:
            difference = Decimal(str(minimum)) - total
            if difference > 0:
                messages.append(f"Minimum : manque {format_price(difference, 2)}")
                warning = True
            else:
                messages.append("Minimum atteint")
        if franco is not None:
            difference = Decimal(str(franco)) - total
            if difference > 0:
                messages.append(f"Franco : manque {format_price(difference, 2)}")
                warning = True
            else:
                messages.append("Franco atteint")
        if not messages:
            messages.append("Seuils non renseignés")
        self.franco_label.configure(
            text=" • ".join(messages),
            foreground=COLORS["warning"] if warning else COLORS["success"],
        )

    def supplier_changed(self) -> None:
        self._hide_supplier_suggestions()
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
        self._update_threshold_label()
        self.search_products()

    def search_products(self, reset_limit=True) -> None:
        if self._search_after:
            self.after_cancel(self._search_after)
            self._search_after = None
        if reset_limit:
            self._product_limit = 100
        self._cancel_product_load()
        supplier_id = self.selected_supplier_id()
        self.product_tree.delete(*self.product_tree.get_children())
        if not supplier_id:
            self.product_status.configure(text="Choisissez un fournisseur.")
            return
        self.product_status.configure(text="Recherche en cours…")
        self._product_search.submit(
            query=self.product_search_var.get(),
            supplier_id=supplier_id,
            favorite_only=not bool(self.product_search_var.get().strip()),
            limit=self._product_limit + 1,
            allow_slow_fallback=True,
            fallback_to_all=True,
        )

    def _show_more_products(self):
        self._product_limit += 100
        self.search_products(reset_limit=False)

    def _products_loaded(self, outcome):
        if outcome.error:
            self.product_status.configure(
                text="Recherche impossible. Consultez le diagnostic."
            )
            return
        result = outcome.result
        self._products_have_more = len(result.rows) > self._product_limit
        self._product_rows = result.rows[: self._product_limit]
        self._product_position = 0
        self._render_products()

    def _render_products(self):
        self._product_render_after = None
        end = min(self._product_position + 25, len(self._product_rows))
        for row in self._product_rows[self._product_position : end]:
            self.product_tree.insert(
                "",
                "end",
                iid=str(row["id"]),
                values=(
                    row["supplier_ref"],
                    row["short_name"] or row["designation"],
                    format_pack(row),
                    format_price(row["unit_price"]),
                ),
            )
        self._product_position = end
        if end < len(self._product_rows):
            self._product_render_after = self.after(1, self._render_products)
            return
        self.product_status.configure(
            text=f"{end} article(s)"
            + (" • d'autres résultats disponibles" if self._products_have_more else "")
        )
        self.more_products.configure(
            state="normal" if self._products_have_more else "disabled"
        )
        self.product_sorter.reapply()

    def add_product(self) -> None:
        selected = self.product_tree.selection()
        if not selected:
            return
        self.add_product_by_id(int(selected[0]))

    def add_product_by_id(self, product_id: int) -> None:
        product = self.database.get_product(product_id)
        if product is None:
            return
        if not product["active"] or product["catalog_review_required"]:
            messagebox.showwarning(
                "Article à vérifier",
                "Cet article est inactif ou ses informations doivent être vérifiées. "
                "Ouvrez Catalogue > Modifier l'article avant de le commander.", parent=self,
            )
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
            (item for item in self.cart if item["product_id"] == int(product["id"])),
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
                    "designation": product["short_name"] or product["designation"],
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
            self.app.sync_team_data()
            self.search_products()
            self.add_product_by_id(dialog.product_id)

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
        self.cart_sorter.reapply()
        self.total_label.configure(text=f"Total HT : {format_price(total, 2)}")
        self._update_threshold_label(total)

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

    def load_order(self, order_id: int, lock: ResourceLock | None = None) -> None:
        order, lines = self.database.get_order(order_id)
        if order["status"] != "Brouillon":
            raise ValueError("Seuls les brouillons peuvent être modifiés.")
        self.current_order_id = order_id
        self.current_order_lock = lock
        self.current_order_date = date.fromisoformat(order["order_date"])
        self.supplier_var.set(order["supplier_name"])
        self._previous_supplier = order["supplier_name"]
        self.notes_var.set(order["notes"] or "")
        self.requester_var.set(order["requester_service"] or "")
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
        self.mode_label.configure(text=f"Modification de {order['order_number']}")
        self.search_products()
        self.refresh_cart()
        self._editor_baseline = self._editor_state()

    def reset_order(self, confirm: bool = True) -> bool:
        if confirm and (self.has_unsaved_changes() or self.current_order_id):
            if not messagebox.askyesno(
                "Nouvelle commande",
                "Effacer la commande affichée et repartir de zéro ?",
                parent=self,
            ):
                return False
        if self.current_order_lock:
            self.current_order_lock.release()
            self.current_order_lock = None
        self.current_order_id = None
        self.current_order_date = None
        self.cart.clear()
        self.notes_var.set("")
        self.requester_var.set("")
        self.supplier_var.set("")
        self._cancel_product_load()
        self.product_search_var.set("")
        self._hide_supplier_suggestions()
        self._previous_supplier = ""
        self.mode_label.configure(text="")
        self.franco_label.configure(text="")
        self.product_tree.delete(*self.product_tree.get_children())
        self.refresh_cart()
        self._editor_baseline = self._editor_state()
        return True

    def _confirm_order_warnings(self, supplier_id: int) -> bool:
        warnings = []
        fractional = fractional_carton_lines(self.cart)
        if fractional:
            sample = "\n".join(f"• {name}" for name in fractional[:5])
            more = "\n…" if len(fractional) > 5 else ""
            warnings.append(
                f"Le nombre de cartons n'est pas entier pour :\n{sample}{more}"
            )
        total = sum(
            (
                Decimal(str(item["cartons"]))
                * Decimal(str(item["units_per_carton"]))
                * Decimal(str(item["unit_price"]))
                for item in self.cart
            ),
            Decimal("0"),
        )
        supplier = self.database.get_supplier(supplier_id)
        if supplier:
            minimum = supplier["minimum_order_ht"]
            franco = supplier["franco_ht"]
            if minimum is not None and total < Decimal(str(minimum)):
                warnings.append(
                    "Le minimum de commande n'est pas atteint "
                    f"({format_price(total, 2)} / {format_price(minimum, 2)})."
                )
            if franco is not None and total < Decimal(str(franco)):
                warnings.append(
                    "Le seuil de franco n'est pas atteint "
                    f"({format_price(total, 2)} / {format_price(franco, 2)})."
                )
        if not warnings:
            return True
        return messagebox.askyesno(
            "Vérification de la commande",
            "\n\n".join(warnings) + "\n\nEnregistrer quand même ?",
            parent=self,
        )

    def _save(self, generate_pdf: bool) -> bool:
        supplier_id = self.selected_supplier_id()
        if not supplier_id:
            messagebox.showwarning(
                "Commande", "Choisissez un fournisseur.", parent=self
            )
            return False
        if not self.cart:
            messagebox.showwarning(
                "Commande", "Ajoutez au moins un article.", parent=self
            )
            return False
        if not self._confirm_order_warnings(supplier_id):
            return False
        editing_order_id = self.current_order_id
        if editing_order_id is not None and self.app.collaboration:
            if self.current_order_lock is None or self.current_order_lock.released:
                messagebox.showwarning(
                    "Verrou perdu",
                    "Cette commande n'est plus réservée sur ce poste. "
                    "Reprenez-la depuis l'historique avant d'enregistrer.",
                    parent=self,
                )
                return False
            try:
                self.current_order_lock.refresh()
            except (OSError, CollaborationError) as exc:
                messagebox.showwarning("Verrou indisponible", str(exc), parent=self)
                return False
        if editing_order_id is None:
            similar = self.database.find_recent_similar_order(
                supplier_id, self.cart, days=7
            )
            if similar is not None and not messagebox.askyesno(
                "Commande similaire récente",
                (
                    f"La commande {similar['order_number']} du "
                    f"{date.fromisoformat(similar['order_date']):%d/%m/%Y} "
                    "contient les mêmes articles.\n\n"
                    "Créer quand même cette nouvelle commande ?"
                ),
                icon="warning",
                parent=self,
            ):
                return False
        try:
            reserved_number = (
                self.app.reserve_order_number(self.current_order_date)
                if editing_order_id is None
                else None
            )
            order_id = self.database.save_order(
                supplier_id=supplier_id,
                lines=self.cart,
                notes=self.notes_var.get(),
                order_id=editing_order_id,
                selected_date=self.current_order_date,
                order_number=reserved_number,
                requester_service=self.requester_var.get(),
            )
        except ValueError as exc:
            messagebox.showwarning("Commande non enregistrée", str(exc), parent=self)
            return False
        except (OSError, CollaborationError) as exc:
            messagebox.showwarning(
                "Commande",
                (
                    "Le numéro de commande partagé ne peut pas être réservé. "
                    "Aucune commande n'a été créée.\n\n"
                    f"{exc}"
                ),
                parent=self,
            )
            return False
        order, _ = self.database.get_order(order_id)
        self.current_order_id = order_id
        self.current_order_date = date.fromisoformat(order["order_date"])
        self._editor_baseline = self._editor_state()
        if self.app.collaboration and self.current_order_lock is None:
            self.current_order_lock = self.app.acquire_order_lock(order_id)
            if self.current_order_lock is None:
                return False
        self.mode_label.configure(text=f"Modification de {order['order_number']}")
        if generate_pdf:
            output = choose_pdf_path(self, self.database, order)
            if output is None:
                messagebox.showinfo(
                    "PDF non généré",
                    "L'enregistrement du PDF a été annulé. "
                    "La commande reste enregistrée comme brouillon.",
                    parent=self,
                )
                self.app.publish_order(order_id)
                self.app.refresh_pages()
                return False
            try:
                generate_order_pdf(self.database, order_id, output)
            except ValueError as exc:
                messagebox.showwarning("Brouillon enregistré, PDF non généré", str(exc), parent=self)
                self.app.publish_order(order_id)
                return False
            open_path(output.parent)
        self.app.publish_order(order_id)
        self.reset_order(confirm=False)
        self.app.refresh_pages()
        return True

    def save_draft(self) -> bool:
        return self._save(generate_pdf=False)

    def save_and_generate(self) -> bool:
        return self._save(generate_pdf=True)

    def refresh(self) -> None:
        if self.has_unsaved_changes():
            return
        self.load_suppliers()
        self.search_products()
        self._valid = True

    def fit_visible_columns(self) -> None:
        self.product_column_sizer.fit()
        self.cart_column_sizer.fit()

    def shutdown(self) -> None:
        if self._search_after:
            self.after_cancel(self._search_after)
        self._cancel_product_load()
        self._product_search.close()


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
            ("Détail du conditionnement", "unit_packaging"),
            ("Prix unitaire HT", "price"),
            ("TVA (%)", "vat"),
        ]
        self.vars = {key: tk.StringVar() for _, key in fields}
        self.vars["pack"].set("1")
        self.vars["vat"].set("20")
        for row, (label, key) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=5)
            ttk.Entry(frame, textvariable=self.vars[key], width=42).grid(
                row=row, column=1, sticky="ew", padx=(10, 0), pady=5
            )
        buttons = ttk.Frame(frame)
        buttons.grid(row=len(fields), column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Annuler", command=self.destroy).pack(side="left")
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
            pack = float(
                parse_decimal(self.vars["pack"].get(), "Conditionnement", minimum=0)
            )
            price = float(parse_decimal(self.vars["price"].get(), "Prix", minimum=0))
            vat = float(
                parse_decimal(self.vars["vat"].get(), "TVA", minimum=0, maximum=100)
            )
            if pack <= 0:
                raise ValueError("Le conditionnement doit être supérieur à zéro.")
            if price < 0 or vat < 0:
                raise ValueError("Le prix et la TVA ne peuvent pas être négatifs.")
            self.product_id = self.database.create_manual_product(
                self.supplier_id,
                self.vars["reference"].get(),
                designation,
                pack,
                price,
                vat,
                self.vars["unit_packaging"].get(),
            )
            self.destroy()
        except ValueError as exc:
            messagebox.showerror("Article", str(exc), parent=self)
