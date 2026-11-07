from __future__ import annotations

import queue
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from ..catalog_search import LatestCatalogSearchWorker, SearchOutcome
from ..database import Database, SearchIndexError, SearchTimeoutError
from ..numbers import parse_decimal
from .base import BasePage
from .common import COLORS
from .components import TreeviewColumnSizer
from .components import TreeviewSorter
from .common import format_number
from .common import format_pack
from .common import format_price
from .common import product_field_display_value
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .order import OrderPage


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
        self.supplier_box.bind(
            "<<ComboboxSelected>>", lambda event: self.search(force=True)
        )
        self.favorite_var = tk.BooleanVar()
        ttk.Checkbutton(
            filters,
            text="Favoris uniquement",
            variable=self.favorite_var,
            command=lambda: self.search(force=True),
        ).pack(side="left", padx=10)
        self.search_button = ttk.Button(
            filters,
            text="Rechercher",
            command=lambda: self.search(force=True),
        )
        self.search_button.pack(side="right")

        review_filters = ttk.Frame(self)
        review_filters.pack(fill="x", pady=(0, 8))
        self.review_only_var = tk.BooleanVar()
        ttk.Checkbutton(
            review_filters,
            text="Articles à vérifier uniquement",
            variable=self.review_only_var,
            command=lambda: self.search(force=True),
        ).pack(side="left")
        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True)
        columns = (
            "favorite",
            "source",
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
            "source": "Origine",
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
            "source": 72,
            "supplier": 135,
            "reference": 95,
            "code": 90,
            "designation": 480,
            "pack": 130,
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
        self.tree.bind("<Double-1>", lambda event: self.edit_product())
        self.tree.bind(
            "<<TreeviewSelect>>", lambda event: self.update_product_actions()
        )
        self.tree_sorter = TreeviewSorter(
            self.tree,
            headings,
            numeric_columns={"pack", "price", "vat"},
        )
        self.tree_column_sizer = TreeviewColumnSizer(
            self.tree,
            widths,
            flexible_column="designation",
            minimum_widths={
                "favorite": 34,
                "source": 58,
                "supplier": 95,
                "reference": 78,
                "code": 78,
                "designation": 220,
                "pack": 90,
                "price": 70,
                "vat": 50,
            },
        )

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", pady=(10, 0))
        self.result_label = ttk.Label(bottom, text="", style="Subtitle.TLabel")
        self.result_label.pack(side="left")
        self.more_button = ttk.Button(
            bottom,
            text="Afficher 100 de plus",
            command=self._show_more,
            state="disabled",
        )
        self.more_button.pack(side="left", padx=8)
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
        self.delete_product_button = ttk.Button(
            bottom,
            text="Supprimer",
            command=self.delete_product,
            state="disabled",
        )
        self.delete_product_button.pack(side="right")
        self.reset_product_button = ttk.Button(
            bottom,
            text="Rétablir CAHPP",
            command=self.reset_product,
            state="disabled",
        )
        self.reset_product_button.pack(side="right", padx=8)
        self.edit_product_button = ttk.Button(
            bottom,
            text="Modifier l'article",
            command=self.edit_product,
        )
        self.edit_product_button.pack(side="right")
        ttk.Button(
            bottom,
            text="Commander cet article",
            style="Accent.TButton",
            command=self.start_order,
        ).pack(side="right")

        self.supplier_map: dict[str, int | None] = {}
        self._after_id: str | None = None
        self._poll_after_id: str | None = None
        self._render_after_id: str | None = None
        self._display_limit = 100
        self._render_rows: list[dict[str, object]] = []
        self._render_position = 0
        self._render_meta: tuple[bool, int, str, bool, str] = (
            False,
            0,
            "",
            False,
            "",
        )
        self._search_generation = 0
        self._search_pending = False
        self._last_search_error = ""
        self._search_results: queue.Queue[SearchOutcome] = queue.Queue()
        self._search_worker = LatestCatalogSearchWorker(
            self.database,
            self._search_results.put,
        )

    def _schedule_search(self, event=None) -> None:
        self._search_generation = self._search_worker.invalidate()
        self._search_pending = False
        self.search_button.configure(state="normal")
        self._cancel_render()
        if self._after_id:
            self.after_cancel(self._after_id)
        self._after_id = None
        self._display_limit = 100
        query = self.search_var.get().strip()
        if query and len(query) < 2:
            self._cancel_render()
            self.tree.delete(*self.tree.get_children())
            self.result_label.configure(
                text="Saisissez au moins 2 caractères.",
                foreground=COLORS["muted"],
            )
            self.more_button.configure(state="disabled")
            return
        self._after_id = self.after(400, self.search)

    def _load_suppliers(self) -> None:
        suppliers = self.database.list_suppliers(used_only=True)
        self.supplier_map = {"Tous les fournisseurs": None}
        self.supplier_map.update({row["name"]: row["id"] for row in suppliers})
        values = list(self.supplier_map)
        current = self.supplier_var.get()
        self.supplier_box["values"] = values
        if current not in self.supplier_map:
            self.supplier_var.set(values[0] if values else "")

    def search(self, force: bool = False, reset_limit: bool = True) -> None:
        if self._after_id:
            self.after_cancel(self._after_id)
        self._after_id = None
        if reset_limit:
            self._display_limit = 100
        query = self.search_var.get().strip()
        if query and len(query) < 2 and not force:
            self.result_label.configure(
                text="Saisissez au moins 2 caractères.",
                foreground=COLORS["muted"],
            )
            return
        supplier_id = self.supplier_map.get(self.supplier_var.get())
        self._cancel_render()
        self.more_button.configure(state="disabled")
        self.result_label.configure(
            text="Recherche en cours…",
            foreground=COLORS["muted"],
        )
        self.search_button.configure(state="disabled")
        self._search_pending = True
        self._search_generation = self._search_worker.submit(
            query=query,
            supplier_id=supplier_id,
            favorite_only=self.favorite_var.get(),
            limit=self._display_limit + 1,
            allow_slow_fallback=force or len(query) >= 3,
            review_only=self.review_only_var.get(),
        )
        self._start_result_polling()

    def _show_more(self) -> None:
        self._display_limit += 100
        self.search(force=True, reset_limit=False)

    def _start_result_polling(self) -> None:
        if self._poll_after_id is None:
            self._poll_after_id = self.after(50, self._poll_search_results)

    def _poll_search_results(self) -> None:
        self._poll_after_id = None
        outcome: SearchOutcome | None = None
        try:
            while True:
                candidate = self._search_results.get_nowait()
                if candidate.generation == self._search_generation:
                    outcome = candidate
        except queue.Empty:
            pass
        if outcome is not None:
            self._search_pending = False
            self.search_button.configure(state="normal")
            self._handle_search_outcome(outcome)
        if self._search_pending:
            self._poll_after_id = self.after(50, self._poll_search_results)

    def _handle_search_outcome(self, outcome: SearchOutcome) -> None:
        if outcome.error is not None:
            error = outcome.error
            if isinstance(error, SearchTimeoutError):
                message = (
                    "La recherche a dépassé le délai autorisé. Précisez votre recherche ; "
                    "si le problème persiste, ouvrez Paramètres > Diagnostic."
                )
            elif isinstance(error, SearchIndexError):
                message = (
                    "Index de recherche indisponible. Consultez "
                    "Paramètres > Diagnostic > Reconstruire l'index."
                )
            else:
                message = f"Recherche impossible : {type(error).__name__}: {error}"
            self.result_label.configure(
                text=message,
                foreground=COLORS["danger"],
            )
            if message != self._last_search_error:
                self._last_search_error = message
                messagebox.showwarning("Recherche catalogue", message, parent=self)
            return
        result = outcome.result
        if result is None:
            return
        self._last_search_error = ""
        has_more = len(result.rows) > self._display_limit
        rows = result.rows[: self._display_limit]
        self._begin_render(
            rows,
            has_more=has_more,
            elapsed_ms=result.elapsed_ms,
            mode=result.mode,
            repaired=result.repaired,
            warning=result.warning,
        )

    def _begin_render(
        self,
        rows: list[dict[str, object]],
        *,
        has_more: bool,
        elapsed_ms: int,
        mode: str,
        repaired: bool,
        warning: str,
    ) -> None:
        self._cancel_render()
        self.tree.delete(*self.tree.get_children())
        self._render_rows = rows
        self._render_position = 0
        self._render_meta = (has_more, elapsed_ms, mode, repaired, warning)
        self._render_next_batch()

    def _render_next_batch(self) -> None:
        self._render_after_id = None
        end = min(self._render_position + 25, len(self._render_rows))
        for row in self._render_rows[self._render_position : end]:
            designation = row["short_name"] or row["designation"]
            self.tree.insert(
                "",
                "end",
                iid=str(row["id"]),
                values=(
                    "★" if row["favorite"] else "",
                    (
                        "Local"
                        if row["source"] == "LOCAL"
                        else "CAHPP ⚠"
                        if row["catalog_review_required"]
                        else "CAHPP ✎"
                        if row["has_override"]
                        else "CAHPP"
                    ),
                    row["supplier_name"],
                    row["supplier_ref"],
                    "—" if row["source"] == "LOCAL" else row["code_cahpp"],
                    designation,
                    format_pack(row),
                    format_price(row["unit_price"]),
                    format_number(row["vat"], 1) + " %",
                ),
            )
        self._render_position = end
        if end < len(self._render_rows):
            self.result_label.configure(
                text=f"Affichage… {end}/{len(self._render_rows)}",
                foreground=COLORS["muted"],
            )
            self._render_after_id = self.after(1, self._render_next_batch)
            return
        has_more, elapsed_ms, mode, repaired, warning = self._render_meta
        details = [f"{len(self._render_rows)} résultat(s)"]
        if has_more:
            details.append("d'autres résultats sont disponibles")
        details.append(f"{elapsed_ms} ms")
        if repaired:
            details.append("index réparé automatiquement")
        elif mode == "like":
            details.append("mode de secours")
        self.result_label.configure(
            text=" • ".join(details),
            foreground=COLORS["warning"]
            if warning or mode == "like"
            else COLORS["muted"],
        )
        self.more_button.configure(state="normal" if has_more else "disabled")
        self.tree_sorter.reapply()
        self.update_product_actions()

    def _cancel_render(self) -> None:
        if self._render_after_id:
            try:
                self.after_cancel(self._render_after_id)
            except tk.TclError:
                pass
            self._render_after_id = None
        self._render_rows = []
        self._render_position = 0

    def selected_product_id(self) -> int | None:
        selected = self.tree.selection()
        return int(selected[0]) if selected else None

    def update_product_actions(self) -> None:
        product_id = self.selected_product_id()
        product = self.database.get_product(product_id) if product_id else None
        self.delete_product_button.configure(
            state=("normal" if product and product["source"] == "LOCAL" else "disabled")
        )
        self.reset_product_button.configure(
            state=("normal" if product and product["has_override"] else "disabled")
        )
        self.edit_product_button.configure(state="normal" if product else "disabled")

    def edit_product(self) -> None:
        product_id = self.selected_product_id()
        if not product_id:
            messagebox.showinfo(
                "Article", "Sélectionnez d'abord un article.", parent=self
            )
            return
        with self.app.locked_product(product_id) as allowed:
            if not allowed:
                return
            dialog = ProductEditDialog(self, self.database, product_id)
            self.wait_window(dialog)
            if dialog.saved:
                self.search()
                self.app.pages["dashboard"].invalidate()
                self.app.sync_team_data()

    def reset_product(self) -> None:
        product_id = self.selected_product_id()
        if not product_id:
            return
        if not messagebox.askyesno(
            "Rétablir les valeurs CAHPP",
            "Supprimer toutes les corrections locales de cet article ?",
            parent=self,
        ):
            return
        with self.app.locked_product(product_id) as allowed:
            if not allowed:
                return
            self.database.reset_product_override(product_id)
        self.search()
        self.app.sync_team_data()

    def delete_product(self) -> None:
        product_id = self.selected_product_id()
        if not product_id:
            return
        product = self.database.get_product(product_id)
        if product is None or product["source"] != "LOCAL":
            return
        if not messagebox.askyesno(
            "Supprimer la référence locale",
            (
                f"Supprimer « {product['designation']} » du catalogue ?\n\n"
                "Les anciennes commandes conserveront cette référence."
            ),
            parent=self,
        ):
            return
        with self.app.locked_product(product_id) as allowed:
            if not allowed:
                return
            self.database.archive_manual_product(product_id)
        self.search()
        self.app.pages["dashboard"].invalidate()
        self.app.sync_team_data()

    def toggle_favorite(self) -> None:
        product_id = self.selected_product_id()
        if not product_id:
            return
        with self.app.locked_product(product_id) as allowed:
            if not allowed:
                return
            product = self.database.get_product(product_id)
            self.database.set_favorite(product_id, not bool(product["favorite"]))
        self.search()
        self.app.pages["dashboard"].invalidate()
        self.app.sync_team_data()

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
        with self.app.locked_product(product_id) as allowed:
            if not allowed:
                return
            self.database.set_favorite(
                product_id,
                True,
                usual_cartons=usual,
                short_name=short_name or "",
            )
        self.search()
        self.app.sync_team_data()

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
        self.search(force=True)
        self._valid = True

    def fit_visible_columns(self) -> None:
        self.tree_column_sizer.fit()

    def shutdown(self) -> None:
        for after_id in (
            self._after_id,
            self._poll_after_id,
            self._render_after_id,
        ):
            if after_id:
                try:
                    self.after_cancel(after_id)
                except tk.TclError:
                    pass
        self._after_id = None
        self._poll_after_id = None
        self._render_after_id = None
        self._search_worker.close()


class ProductEditDialog(tk.Toplevel):
    def __init__(self, parent, database: Database, product_id: int):
        super().__init__(parent)
        self.database = database
        self.product_id = product_id
        self.product = database.get_product(product_id)
        self.saved = False
        if self.product is None:
            self.destroy()
            return

        source_label = (
            "Référence créée par l'utilisateur"
            if self.product["source"] == "LOCAL"
            else "Article CAHPP — les valeurs d'origine restent conservées"
        )
        self.title("Modifier l'article")
        self.geometry("680x620")
        self.minsize(600, 560)
        self.transient(parent.winfo_toplevel())
        self.grab_set()

        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True)
        footer = ttk.Frame(outer, padding=(20, 10))
        footer.pack(side="bottom", fill="x")
        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)
        canvas = tk.Canvas(body, highlightthickness=0, background=COLORS["background"])
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        surface = ttk.Frame(canvas, padding=20)
        window = canvas.create_window(0, 0, anchor="nw", window=surface)
        surface.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        self.bind("<MouseWheel>", lambda event: canvas.yview_scroll(int(-event.delta / 120), "units"))
        self.bind("<Button-4>", lambda event: canvas.yview_scroll(-1, "units"))
        self.bind("<Button-5>", lambda event: canvas.yview_scroll(1, "units"))
        ttk.Label(
            surface,
            text=str(self.product["designation"]),
            font=("Segoe UI Semibold", 14),
            wraplength=570,
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            surface,
            text=source_label,
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 14))

        definitions = [
            ("Référence fournisseur", "supplier_ref"),
            ("Désignation", "designation"),
            ("Conditionnement", "conditionnement"),
            ("Détail du conditionnement", "unit_packaging"),
            ("Prix unitaire HT", "unit_price"),
            ("TVA (%)", "vat"),
            ("Note interne", "internal_notes"),
            ("Code CAHPP de remplacement", "replacement_code_cahpp"),
        ]
        self.vars: dict[str, tk.StringVar] = {}
        for row, (label, key) in enumerate(definitions, start=2):
            ttk.Label(surface, text=label).grid(row=row, column=0, sticky="w", pady=7)
            variable = tk.StringVar(
                value=product_field_display_value(key, self.product[key])
            )
            ttk.Entry(surface, textvariable=variable, width=52).grid(
                row=row, column=1, sticky="ew", padx=(14, 0), pady=7
            )
            self.vars[key] = variable

        if self.product["source"] == "CAHPP":
            ttk.Label(
                surface,
                text=(
                    "Les champs identiques au catalogue ne créent aucune "
                    "correction locale. Le bouton « Rétablir CAHPP » permet "
                    "ensuite d'annuler toutes les corrections."
                ),
                style="Subtitle.TLabel",
                wraplength=570,
            ).grid(
                row=2 + len(definitions),
                column=0,
                columnspan=2,
                sticky="w",
                pady=(12, 0),
            )

        self.review_confirmed_var = tk.BooleanVar()
        if self.product["catalog_review_required"]:
            ttk.Label(
                surface,
                text=self.product["catalog_review_reason"]
                + " Vérifiez les valeurs auprès du fournisseur avant de confirmer.",
                wraplength=570,
                foreground=COLORS["warning"],
            ).grid(
                row=3 + len(definitions),
                column=0,
                columnspan=2,
                sticky="w",
                pady=(10, 4),
            )
            ttk.Checkbutton(
                surface,
                text="J'ai vérifié les informations et corrigé les valeurs ci-dessus.",
                variable=self.review_confirmed_var,
            ).grid(row=4 + len(definitions), column=0, columnspan=2, sticky="w")
        actions = footer
        ttk.Button(actions, text="Annuler", command=self.destroy).pack(side="left")
        self.save_button = ttk.Button(
            actions,
            text="Enregistrer",
            style="Accent.TButton",
            command=self.save,
        )
        self.save_button.pack(side="left", padx=(8, 0))
        surface.columnconfigure(1, weight=1)

    def save(self) -> None:
        try:
            if (
                self.product["catalog_review_required"]
                and not self.review_confirmed_var.get()
            ):
                raise ValueError(
                    "Vérifiez les valeurs puis cochez la confirmation des informations."
                )
            designation = self.vars["designation"].get().strip()
            if not designation:
                raise ValueError("La désignation est obligatoire.")
            conditionnement = float(
                parse_decimal(
                    self.vars["conditionnement"].get(), "Conditionnement", minimum=0
                )
            )
            unit_price = float(
                parse_decimal(self.vars["unit_price"].get(), "Prix", minimum=0)
            )
            vat = float(
                parse_decimal(self.vars["vat"].get(), "TVA", minimum=0, maximum=100)
            )
            if conditionnement <= 0:
                raise ValueError("Le conditionnement doit être supérieur à zéro.")
            if unit_price < 0 or vat < 0:
                raise ValueError("Le prix et la TVA ne peuvent pas être négatifs.")

            values = {
                "supplier_ref": self.vars["supplier_ref"].get(),
                "designation": designation,
                "conditionnement": conditionnement,
                "unit_packaging": self.vars["unit_packaging"].get(),
                "unit_price": unit_price,
                "vat": vat,
            }
            if self.product["source"] == "LOCAL":
                self.database.update_manual_product(self.product_id, **values)
            else:
                self.database.set_product_override(
                    self.product_id,
                    **values,
                    catalog_review_confirmed=self.review_confirmed_var.get(),
                    reviewed_catalog_token=self.product["catalog_review_token"],
                )
            self.database.update_product_team_details(
                self.product_id,
                internal_notes=self.vars["internal_notes"].get(),
                replacement_code_cahpp=self.vars["replacement_code_cahpp"].get(),
            )
            self.saved = True
            self.destroy()
        except ValueError as exc:
            messagebox.showerror("Article", str(exc), parent=self)
