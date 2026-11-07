from __future__ import annotations

import json
import tkinter as tk
import webbrowser
from datetime import date
from tkinter import messagebox, simpledialog, ttk
from ..collaboration import CollaborationError
from ..database import Database
from ..local_services import (
    delete_unsent_order,
    mark_order_sent,
    prepare_mail_order,
    resolve_portable_path,
)
from ..pdf_export import generate_order_pdf
from .base import BasePage
from .components import FeedbackButton
from .documents import OrderDocumentsDialog
from .tracking import OrderTrackingDialog
from .common import centered_window_position
from .common import choose_pdf_path
from .common import format_number
from .common import format_price
from .common import format_timestamp
from .common import open_path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .order import OrderPage


class SelectiveDuplicateDialog(tk.Toplevel):
    def __init__(self, parent, database: Database, order_id: int):
        super().__init__(parent)
        self.withdraw()
        self.result: list[str] | None = None
        order, lines = database.get_order(order_id)
        self.title(f"Recommander — {order['order_number']}")
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        content = ttk.Frame(self, padding=18)
        content.pack(fill="both", expand=True)
        ttk.Label(
            content,
            text="Choisissez les articles à reprendre",
            font=("Segoe UI Semibold", 14),
        ).pack(anchor="w")
        ttk.Label(
            content,
            text="Utilisez Ctrl ou Maj pour sélectionner plusieurs lignes.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 10))
        self.tree = ttk.Treeview(
            content,
            columns=("ref", "designation", "cartons", "units"),
            show="headings",
            selectmode="extended",
        )
        for column, title, width, anchor in (
            ("ref", "Référence", 130, "center"),
            ("designation", "Désignation", 480, "w"),
            ("cartons", "Cartons", 90, "center"),
            ("units", "Unités", 90, "center"),
        ):
            self.tree.heading(column, text=title)
            self.tree.column(
                column,
                width=width,
                anchor=anchor,
                stretch=column == "designation",
            )
        for line in lines:
            self.tree.insert(
                "",
                "end",
                iid=str(line["line_uid"]),
                values=(
                    line["supplier_ref"] or "—",
                    line["designation"],
                    format_number(line["cartons"], 2),
                    format_number(line["total_units"], 2),
                ),
            )
        self.tree.pack(fill="both", expand=True)
        self.tree.selection_set(self.tree.get_children())
        selection_actions = ttk.Frame(content)
        selection_actions.pack(fill="x", pady=(8, 12))
        ttk.Button(
            selection_actions,
            text="Tout sélectionner",
            command=lambda: self.tree.selection_set(self.tree.get_children()),
        ).pack(side="left")
        ttk.Button(
            selection_actions,
            text="Tout désélectionner",
            command=lambda: self.tree.selection_remove(self.tree.get_children()),
        ).pack(side="left", padx=7)
        buttons = ttk.Frame(content)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Annuler", command=self.destroy).pack(side="right")
        ttk.Button(
            buttons,
            text="Créer le brouillon",
            style="Accent.TButton",
            command=self.validate,
        ).pack(side="right", padx=7)
        self.update_idletasks()
        width, height = 900, 580
        owner = parent.winfo_toplevel()
        x, y = centered_window_position(
            owner.winfo_rootx(),
            owner.winfo_rooty(),
            owner.winfo_width(),
            owner.winfo_height(),
            width,
            height,
            self.winfo_screenwidth(),
            self.winfo_screenheight(),
        )
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(760, 480)
        self.deiconify()

    def validate(self) -> None:
        selected = list(self.tree.selection())
        if not selected:
            messagebox.showinfo(
                "Recommander", "Sélectionnez au moins un article.", parent=self
            )
            return
        self.result = selected
        self.destroy()


class OrdersPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header(
            "Historique des commandes",
            "Recherchez, dupliquez et consultez les documents associés.",
        )
        saved_filters = ttk.Frame(self)
        saved_filters.pack(fill="x", pady=(0, 7))
        ttk.Label(saved_filters, text="Filtres enregistrés").pack(side="left")
        self.saved_filter_var = tk.StringVar()
        self.saved_filter_box = ttk.Combobox(
            saved_filters,
            textvariable=self.saved_filter_var,
            state="readonly",
            width=28,
        )
        self.saved_filter_box.pack(side="left", padx=(7, 5))
        self.saved_filter_box.bind(
            "<<ComboboxSelected>>", lambda event: self.apply_saved_filter()
        )
        ttk.Button(
            saved_filters, text="Appliquer", command=self.apply_saved_filter
        ).pack(side="left")
        ttk.Button(
            saved_filters, text="Enregistrer l'affichage…", command=self.save_filter
        ).pack(side="left", padx=5)
        ttk.Button(saved_filters, text="Supprimer", command=self.delete_filter).pack(
            side="left"
        )
        filters = ttk.Frame(self)
        filters.pack(fill="x", pady=(0, 10))
        ttk.Label(filters, text="Recherche").pack(side="left")
        self.search_var = tk.StringVar()
        search = ttk.Entry(filters, textvariable=self.search_var, width=42)
        search.pack(side="left", padx=(7, 14))
        search.bind("<KeyRelease>", self._schedule_refresh)
        ttk.Label(filters, text="Statut").pack(side="left")
        self.status_var = tk.StringVar(value="Tous")
        status_box = ttk.Combobox(
            filters,
            textvariable=self.status_var,
            state="readonly",
            width=18,
            values=(
                "Tous",
                "Brouillon",
                "Générée",
                "E-mail préparé",
                "Envoyée",
                "Confirmée",
                "Partiellement livrée",
                "Livrée",
                "Facturée",
            ),
        )
        status_box.pack(side="left", padx=7)
        status_box.bind("<<ComboboxSelected>>", lambda event: self.refresh())
        ttk.Label(filters, text="Livraison").pack(side="left", padx=(10, 0))
        self.delivery_var = tk.StringVar(value="Toutes")
        delivery_box = ttk.Combobox(
            filters,
            textvariable=self.delivery_var,
            state="readonly",
            width=20,
            values=(
                "Toutes",
                "À recevoir",
                "En attente",
                "Partiellement livrée",
                "Livrée",
                "Non suivie",
            ),
        )
        delivery_box.pack(side="left", padx=7)
        delivery_box.bind("<<ComboboxSelected>>", lambda event: self.refresh())
        self.include_archived_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            filters,
            text="Inclure les archives",
            variable=self.include_archived_var,
            command=self.refresh,
        ).pack(side="left", padx=8)
        self.result_label = ttk.Label(filters, text="", style="Subtitle.TLabel")
        self.result_label.pack(side="right")

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            frame,
            columns=(
                "number",
                "created",
                "author",
                "sent",
                "supplier",
                "status",
                "delivery",
                "archive",
                "sync",
                "ht",
                "ttc",
            ),
            show="headings",
        )
        for column, title, width in (
            ("number", "N° commande", 115),
            ("created", "Créée le", 120),
            ("author", "Créée par", 80),
            ("sent", "Envoyée le", 120),
            ("supplier", "Fournisseur", 150),
            ("status", "Statut", 85),
            ("delivery", "Livraison", 80),
            ("archive", "Archivée", 62),
            ("sync", "Synchro", 82),
            ("ht", "Total HT", 82),
            ("ttc", "Total TTC", 82),
        ):
            self.tree.heading(column, text=title)
            self.tree.column(
                column,
                width=width,
                stretch=column == "supplier",
                anchor="w" if column == "supplier" else "center",
            )
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda event: self.edit_draft())
        self.tree.bind("<<TreeviewSelect>>", lambda event: self.update_action_labels())
        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(
            actions,
            text="Reprendre / corriger",
            style="Accent.TButton",
            command=self.edit_draft,
        ).pack(side="left")
        ttk.Button(
            actions,
            text="Recommander",
            command=self.duplicate,
        ).pack(side="left", padx=6)
        ttk.Button(
            actions,
            text="Supprimer",
            command=self.delete_selected_order,
        ).pack(side="left")
        ttk.Button(
            actions,
            text="Documents",
            command=self.manage_documents,
        ).pack(side="left", padx=6)
        ttk.Button(
            actions,
            text="Journal",
            command=self.show_audit,
        ).pack(side="left", padx=6)
        ttk.Button(
            actions,
            text="Préparer le mail",
            style="Accent.TButton",
            command=self.prepare_email,
        ).pack(side="right")
        ttk.Button(actions, text="Marquer envoyée", command=self.mark_sent).pack(
            side="right", padx=6
        )
        self.delivery_button = ttk.Button(
            actions, text="Suivi / réception…", command=self.manage_tracking
        )
        self.delivery_button.pack(side="right")
        ttk.Button(actions, text="Ouvrir le PDF", command=self.open_pdf).pack(
            side="right"
        )
        self.regenerate_button = FeedbackButton(
            actions,
            text="Régénérer la commande",
            command=self.regenerate_pdf,
            success_text="✓ Commande régénérée",
        )
        self.regenerate_button.pack(side="right", padx=6)
        self._refresh_after = None
        self.load_saved_filters()

    def load_saved_filters(self) -> None:
        names = [row["name"] for row in self.database.list_saved_order_filters()]
        self.saved_filter_box["values"] = names
        if self.saved_filter_var.get() not in names:
            self.saved_filter_var.set("")

    def apply_saved_filter(self) -> None:
        name = self.saved_filter_var.get().strip()
        if not name:
            return
        selected = next(
            (
                row
                for row in self.database.list_saved_order_filters()
                if row["name"] == name
            ),
            None,
        )
        if selected is None:
            return
        self.search_var.set(selected["query"] or "")
        self.status_var.set(selected["status"] or "Tous")
        self.delivery_var.set(selected["delivery_status"] or "Toutes")
        self.include_archived_var.set(bool(selected["include_archived"]))
        self.refresh()

    def save_filter(self) -> None:
        name = simpledialog.askstring(
            "Enregistrer le filtre",
            "Nom de cet affichage :",
            parent=self,
            initialvalue=self.saved_filter_var.get(),
        )
        if not name:
            return
        try:
            self.database.save_order_filter(
                name,
                self.search_var.get(),
                self.status_var.get(),
                self.delivery_var.get(),
                self.include_archived_var.get(),
            )
        except ValueError as exc:
            messagebox.showerror("Filtre", str(exc), parent=self)
            return
        self.load_saved_filters()
        self.saved_filter_var.set(name.strip())

    def delete_filter(self) -> None:
        name = self.saved_filter_var.get().strip()
        if not name:
            return
        if not messagebox.askyesno(
            "Supprimer le filtre", f"Supprimer le filtre « {name} » ?", parent=self
        ):
            return
        self.database.delete_order_filter(name)
        self.load_saved_filters()

    def _schedule_refresh(self, event=None) -> None:
        if self._refresh_after:
            self.after_cancel(self._refresh_after)
        self._refresh_after = self.after(250, self.refresh)

    def selected_order(self):
        selected = self.tree.selection()
        return int(selected[0]) if selected else None

    def select_order(self, order_id: int) -> None:
        iid = str(order_id)
        if self.tree.exists(iid):
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)
            self.update_action_labels()

    def update_action_labels(self) -> None:
        order_id = self.selected_order()
        if not order_id:
            self.delivery_button.configure(state="disabled")
            return
        order, _ = self.database.get_order(order_id)
        self.delivery_button.configure(
            state="normal" if order["sent_at"] else "disabled"
        )

    def edit_draft(self) -> None:
        order_id = self.selected_order()
        if not order_id:
            return
        order, _ = self.database.get_order(order_id)
        if not self.database.can_delete_unsent_order(order):
            messagebox.showinfo(
                "Modification",
                "Cette commande a été envoyée ou suivie et ne peut plus être modifiée. "
                "Utilisez Recommander pour créer une nouvelle commande.",
                parent=self,
            )
            return
        order_page: OrderPage = self.app.pages["new_order"]
        if order_page.current_order_id == order_id:
            self.app.show_page("new_order")
            return
        if (
            order_page.has_unsaved_changes() or order_page.current_order_id
        ) and not messagebox.askyesno(
            "Commande en cours",
            "Remplacer la commande affichée dans la préparation ? "
            "Les modifications non enregistrées seront perdues.",
            parent=self,
        ):
            return
        if order["status"] != "Brouillon" and not messagebox.askyesno(
            "Reprendre avant envoi",
            "La commande redeviendra un brouillon en conservant son numéro.\n\n"
            "L'ancien PDF et le mail préparé deviendront obsolètes. Supprimez tout "
            "brouillon dans votre messagerie et régénérez le PDF après correction.\n\n"
            "Confirmez-vous que cette commande n'a pas encore été envoyée ?",
            icon="warning",
            parent=self,
        ):
            return
        lock = self.app.acquire_order_lock(order_id)
        if self.app.collaboration and lock is None:
            return
        try:
            self.database.reopen_unsent_order(order_id)
        except ValueError as exc:
            if lock:
                lock.release()
            messagebox.showwarning("Reprise impossible", str(exc), parent=self)
            return
        # Le brouillon repris est publié tant que son verrou nous appartient.
        self.app.publish_order(order_id)
        order_page.reset_order(confirm=False)
        self.app.show_page("new_order")
        order_page.load_order(order_id, lock=lock)

    def duplicate(self) -> None:
        order_id = self.selected_order()
        if not order_id:
            messagebox.showinfo("Dupliquer", "Sélectionnez une commande.", parent=self)
            return
        dialog = SelectiveDuplicateDialog(self, self.database, order_id)
        self.wait_window(dialog)
        if not dialog.result:
            return
        try:
            reserved = self.app.reserve_order_number(date.today())
            new_id = self.database.duplicate_order_lines(
                order_id, dialog.result, order_number=reserved
            )
        except (OSError, ValueError, CollaborationError) as exc:
            messagebox.showwarning(
                "Dupliquer",
                f"La nouvelle commande n'a pas pu être créée :\n{exc}",
                parent=self,
            )
            return
        lock = self.app.acquire_order_lock(new_id)
        if self.app.collaboration and lock is None:
            return
        self.app.publish_order(new_id)
        self.app.refresh_pages()
        self.app.show_page("new_order")
        order_page: OrderPage = self.app.pages["new_order"]  # type: ignore[assignment]
        order_page.load_order(new_id, lock=lock)

    def manage_documents(self) -> None:
        order_id = self.selected_order()
        if not order_id:
            messagebox.showinfo("Documents", "Sélectionnez une commande.", parent=self)
            return
        with self.app.locked_order(order_id) as allowed:
            if not allowed:
                return
            dialog = OrderDocumentsDialog(self, self.database, order_id)
            self.wait_window(dialog)
            self.app.publish_order(order_id)
        self.refresh()

    def delete_selected_order(self) -> None:
        order_id = self.selected_order()
        if not order_id:
            messagebox.showinfo(
                "Supprimer", "Sélectionnez une commande non envoyée.", parent=self
            )
            return
        order, _ = self.database.get_order(order_id)
        if not self.database.can_delete_unsent_order(order):
            messagebox.showinfo(
                "Supprimer",
                "Une commande envoyée ou déjà suivie ne peut pas être supprimée.",
                parent=self,
            )
            return
        if not messagebox.askyesno(
            "Supprimer la commande non envoyée",
            (
                f"Supprimer la commande non envoyée "
                f"{order['order_number']} ?\n\n"
                "La suppression sera répercutée sur les autres postes.\n\n"
                "Les PDF exportés restent sur le disque. Si un e-mail a été "
                "préparé, supprimez aussi son brouillon dans votre messagerie."
            ),
            icon="warning",
            parent=self,
        ):
            return
        with self.app.locked_order(order_id) as allowed:
            if not allowed:
                return
            try:
                delete_unsent_order(self.database, order_id)
            except (OSError, ValueError) as exc:
                messagebox.showerror("Supprimer la commande", str(exc), parent=self)
                return
            self.app.publish_order(order_id)
        self.app.refresh_pages()
        self.refresh()

    def show_audit(self) -> None:
        order_id = self.selected_order()
        if not order_id:
            messagebox.showinfo("Journal", "Sélectionnez une commande.", parent=self)
            return
        order, _ = self.database.get_order(order_id)
        dialog = tk.Toplevel(self)
        dialog.title(f"Journal — {order['order_number']}")
        dialog.geometry("780x430")
        dialog.minsize(650, 330)
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        content = ttk.Frame(dialog, padding=16)
        content.pack(fill="both", expand=True)
        ttk.Label(
            content,
            text=f"Activité de {order['order_number']}",
            font=("Segoe UI Semibold", 13),
        ).pack(anchor="w", pady=(0, 10))

        frame = ttk.Frame(content)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(
            frame,
            columns=("date", "user", "action", "details"),
            show="headings",
        )
        for column, title, width in (
            ("date", "Date", 135),
            ("user", "Utilisateur", 120),
            ("action", "Action", 145),
            ("details", "Détails", 330),
        ):
            tree.heading(column, text=title)
            tree.column(
                column,
                width=width,
                stretch=column == "details",
                anchor="w",
            )
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        action_labels = {
            "created": "Commande créée",
            "updated": "Commande modifiée",
            "duplicated": "Commande dupliquée",
            "pdf_generated": "PDF généré",
            "status_changed": "Statut modifié",
            "attachment_added": "Document ajouté",
            "attachment_updated": "Document modifié",
            "attachment_deleted": "Document supprimé",
            "synced": "Synchronisation",
        }
        for audit in self.database.list_order_audit(order_id):
            details = str(audit["details"] or "")
            try:
                parsed = json.loads(details) if details else {}
                if isinstance(parsed, dict):
                    details = ", ".join(
                        f"{key} : {value}" for key, value in parsed.items()
                    )
            except json.JSONDecodeError:
                pass
            tree.insert(
                "",
                "end",
                values=(
                    format_timestamp(audit["occurred_at"]),
                    audit["actor_name"] or "—",
                    action_labels.get(audit["action"], audit["action"]),
                    details or "—",
                ),
            )
        ttk.Button(content, text="Fermer", command=dialog.destroy).pack(
            anchor="e", pady=(10, 0)
        )

    def open_pdf(self) -> None:
        order_id = self.selected_order()
        if not order_id:
            return
        order, _ = self.database.get_order(order_id)
        pdf_path = (
            resolve_portable_path(order["pdf_path"]) if order["pdf_path"] else None
        )
        if pdf_path and pdf_path.is_file():
            open_path(pdf_path)
        else:
            messagebox.showinfo("PDF", "Aucun PDF n'a encore été généré.", parent=self)

    def regenerate_pdf(self) -> bool:
        order_id = self.selected_order()
        if not order_id:
            return False
        with self.app.locked_order(order_id) as allowed:
            if not allowed:
                return False
            order, _ = self.database.get_order(order_id)
            output = choose_pdf_path(self, self.database, order)
            if output is None:
                return False
            try:
                generate_order_pdf(self.database, order_id, output)
            except ValueError as exc:
                messagebox.showwarning("PDF non généré", str(exc), parent=self)
                return False
            self.app.publish_order(order_id)
            self.refresh()
            open_path(output.parent)
            return True

    def prepare_email(self) -> None:
        order_id = self.selected_order()
        if not order_id:
            messagebox.showinfo("E-mail", "Sélectionnez une commande.", parent=self)
            return
        with self.app.locked_order(order_id) as allowed:
            if not allowed:
                return
            try:
                compose_url, folder, _ = prepare_mail_order(self.database, order_id)
            except (ValueError, OSError) as exc:
                messagebox.showwarning("E-mail", str(exc), parent=self)
                return
            self.database.update_order_status(order_id, "E-mail préparé")
            self.app.publish_order(order_id)
            webbrowser.open(compose_url)
            open_path(folder)
        self.refresh()

    def mark_sent(self) -> None:
        order_id = self.selected_order()
        if not order_id:
            return
        with self.app.locked_order(order_id) as allowed:
            if not allowed:
                return
            try:
                mark_order_sent(self.database, order_id)
            except OSError as exc:
                messagebox.showwarning(
                    "Nettoyage du dossier d'envoi",
                    (
                        "La commande a été marquée comme envoyée, mais son dossier "
                        f"de préparation n'a pas pu être supprimé :\n{exc}"
                    ),
                    parent=self,
                )
            self.app.publish_order(order_id)
        self.refresh()

    def manage_tracking(self) -> None:
        order_id = self.selected_order()
        if not order_id:
            return
        with self.app.locked_order(order_id) as allowed:
            if not allowed:
                return
            dialog = OrderTrackingDialog(self, self.database, order_id)
            self.wait_window(dialog)
            if dialog.changed:
                self.app.publish_order(order_id)
        self.app.refresh_pages()
        self.refresh()
        self.select_order(order_id)

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        status = self.status_var.get()
        orders = self.database.list_orders(
            query=self.search_var.get(),
            status="" if status == "Tous" else status,
            delivery_status=(
                "" if self.delivery_var.get() == "Toutes" else self.delivery_var.get()
            ),
            include_archived=self.include_archived_var.get(),
        )
        for order in orders:
            self.tree.insert(
                "",
                "end",
                iid=str(order["id"]),
                values=(
                    order["order_number"],
                    format_timestamp(order["created_at"]),
                    order["created_by"] or "—",
                    format_timestamp(order["sent_at"]),
                    order["supplier_name"],
                    order["status"],
                    order["delivery_status"],
                    "Oui" if order["archived_at"] else "—",
                    order["sync_state"],
                    format_price(order["total_ht"], 2),
                    format_price(order["total_ttc"], 2),
                ),
            )
        self.result_label.configure(text=f"{len(orders)} commande(s)")
        self.update_action_labels()
        self._valid = True
