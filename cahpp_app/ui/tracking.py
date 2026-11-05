from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import messagebox, simpledialog, ttk
from ..database import Database
from .common import centered_window_position
from .common import format_number
from .common import format_timestamp


class ReceiptEntryDialog(tk.Toplevel):
    def __init__(self, parent, database: Database, order_id: int):
        super().__init__(parent)
        self.withdraw()
        self.database = database
        self.order_id = order_id
        self.saved = False
        self.quantities: dict[str, float] = {}
        summary = database.receipt_summary(order_id)
        order = summary["order"]
        self.lines = {str(row["line_uid"]): row for row in summary["lines"]}
        self.title(f"Nouvelle réception — {order['order_number']}")
        self.transient(parent)
        self.grab_set()

        content = ttk.Frame(self, padding=18)
        content.pack(fill="both", expand=True)
        ttk.Label(
            content,
            text=f"Réception de {order['order_number']}",
            font=("Segoe UI Semibold", 14),
        ).pack(anchor="w")
        ttk.Label(
            content,
            text="Saisissez uniquement les quantités reçues lors de cette livraison.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 12))

        fields = ttk.Frame(content)
        fields.pack(fill="x", pady=(0, 10))
        ttk.Label(fields, text="Date").pack(side="left")
        self.date_var = tk.StringVar(value=date.today().isoformat())
        ttk.Entry(fields, textvariable=self.date_var, width=13).pack(
            side="left", padx=(6, 16)
        )
        ttk.Label(fields, text="N° BL / référence").pack(side="left")
        self.reference_var = tk.StringVar()
        ttk.Entry(fields, textvariable=self.reference_var, width=28).pack(
            side="left", padx=(6, 0)
        )

        frame = ttk.Frame(content)
        frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            frame,
            columns=(
                "ref",
                "designation",
                "ordered",
                "received",
                "remaining",
                "current",
            ),
            show="headings",
            selectmode="browse",
        )
        for column, title, width, anchor in (
            ("ref", "Référence", 120, "center"),
            ("designation", "Désignation", 390, "w"),
            ("ordered", "Commandé", 90, "center"),
            ("received", "Déjà reçu", 90, "center"),
            ("remaining", "Reliquat", 90, "center"),
            ("current", "Cette réception", 105, "center"),
        ):
            self.tree.heading(column, text=title)
            self.tree.column(
                column,
                width=width,
                anchor=anchor,
                stretch=column == "designation",
            )
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda event: self.edit_quantity())

        line_actions = ttk.Frame(content)
        line_actions.pack(fill="x", pady=(8, 10))
        ttk.Button(
            line_actions, text="Saisir la quantité…", command=self.edit_quantity
        ).pack(side="left")
        ttk.Button(
            line_actions, text="Recevoir tout le reliquat", command=self.receive_all
        ).pack(side="left", padx=7)
        ttk.Button(
            line_actions, text="Effacer les saisies", command=self.clear_quantities
        ).pack(side="left")

        ttk.Label(content, text="Note de réception").pack(anchor="w")
        self.notes_var = tk.StringVar()
        ttk.Entry(content, textvariable=self.notes_var).pack(fill="x", pady=(4, 12))
        buttons = ttk.Frame(content)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Annuler", command=self.destroy).pack(side="right")
        ttk.Button(
            buttons,
            text="Enregistrer la réception",
            style="Accent.TButton",
            command=self.validate,
        ).pack(side="right", padx=7)
        self.refresh_lines()
        self.update_idletasks()
        width, height = 1050, 650
        x, y = centered_window_position(
            parent.winfo_rootx(),
            parent.winfo_rooty(),
            parent.winfo_width(),
            parent.winfo_height(),
            width,
            height,
            self.winfo_screenwidth(),
            self.winfo_screenheight(),
        )
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(900, 560)
        self.deiconify()

    def selected_line_uid(self) -> str | None:
        selected = self.tree.selection()
        return str(selected[0]) if selected else None

    def edit_quantity(self) -> None:
        line_uid = self.selected_line_uid()
        if not line_uid:
            messagebox.showinfo("Réception", "Sélectionnez un article.", parent=self)
            return
        line = self.lines[line_uid]
        remaining = float(line["remaining_units"] or 0)
        if remaining <= 0:
            return
        quantity = simpledialog.askfloat(
            "Quantité reçue",
            f"{line['designation']}\nQuantité encore attendue : {remaining:g}",
            parent=self,
            initialvalue=self.quantities.get(line_uid, remaining),
            minvalue=0,
            maxvalue=remaining,
        )
        if quantity is None:
            return
        if quantity > 0:
            self.quantities[line_uid] = quantity
        else:
            self.quantities.pop(line_uid, None)
        self.refresh_lines()
        self.tree.selection_set(line_uid)

    def receive_all(self) -> None:
        self.quantities = {
            line_uid: float(line["remaining_units"] or 0)
            for line_uid, line in self.lines.items()
            if float(line["remaining_units"] or 0) > 0
        }
        self.refresh_lines()

    def clear_quantities(self) -> None:
        self.quantities.clear()
        self.refresh_lines()

    def refresh_lines(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for line_uid, line in self.lines.items():
            self.tree.insert(
                "",
                "end",
                iid=line_uid,
                values=(
                    line["supplier_ref"] or "—",
                    line["designation"],
                    format_number(line["total_units"], 2),
                    format_number(line["received_units"], 2),
                    format_number(line["remaining_units"], 2),
                    format_number(self.quantities.get(line_uid, 0), 2),
                ),
            )

    def validate(self) -> None:
        try:
            selected_date = date.fromisoformat(self.date_var.get().strip())
            self.database.add_receipt(
                self.order_id,
                selected_date,
                self.quantities,
                reference=self.reference_var.get(),
                notes=self.notes_var.get(),
            )
        except ValueError as exc:
            messagebox.showerror("Réception", str(exc), parent=self)
            return
        self.saved = True
        self.destroy()


class OrderTrackingDialog(tk.Toplevel):
    def __init__(self, parent, database: Database, order_id: int):
        super().__init__(parent)
        self.withdraw()
        self.database = database
        self.order_id = order_id
        self.changed = False
        order, _ = database.get_order(order_id)
        self.title(f"Suivi — {order['order_number']}")
        self.transient(parent.winfo_toplevel())
        self.grab_set()

        content = ttk.Frame(self, padding=18)
        content.pack(fill="both", expand=True)
        header = ttk.Frame(content)
        header.pack(fill="x", pady=(0, 12))
        self.title_label = ttk.Label(
            header,
            text=f"Suivi de {order['order_number']}",
            font=("Segoe UI Semibold", 14),
        )
        self.title_label.pack(side="left")
        self.status_label = ttk.Label(header, text="", style="Subtitle.TLabel")
        self.status_label.pack(side="right")

        milestones = ttk.Frame(content, style="Surface.TFrame", padding=12)
        milestones.pack(fill="x", pady=(0, 12))
        ttk.Label(milestones, text="Livraison prévue", style="Surface.TLabel").pack(
            side="left"
        )
        self.expected_var = tk.StringVar()
        ttk.Entry(milestones, textvariable=self.expected_var, width=13).pack(
            side="left", padx=(6, 5)
        )
        ttk.Button(
            milestones, text="Enregistrer la date", command=self.save_expected_date
        ).pack(side="left", padx=(0, 12))
        self.confirm_button = ttk.Button(
            milestones, text="Marquer confirmée", command=self.toggle_confirmation
        )
        self.confirm_button.pack(side="left")
        self.invoice_button = ttk.Button(
            milestones, text="Marquer facturée", command=self.toggle_invoice
        )
        self.invoice_button.pack(side="left", padx=7)
        ttk.Label(
            milestones,
            text="Date au format AAAA-MM-JJ",
            style="Surface.TLabel",
        ).pack(side="right")

        notebook = ttk.Notebook(content)
        notebook.pack(fill="both", expand=True)
        deliveries_tab = ttk.Frame(notebook, padding=10)
        comments_tab = ttk.Frame(notebook, padding=10)
        notebook.add(deliveries_tab, text="Réceptions et reliquats")
        notebook.add(comments_tab, text="Notes internes")

        self.lines_tree = ttk.Treeview(
            deliveries_tab,
            columns=("ref", "designation", "ordered", "received", "remaining"),
            show="headings",
            height=9,
        )
        for column, title, width, anchor in (
            ("ref", "Référence", 120, "center"),
            ("designation", "Désignation", 460, "w"),
            ("ordered", "Commandé", 100, "center"),
            ("received", "Reçu", 100, "center"),
            ("remaining", "Reliquat", 100, "center"),
        ):
            self.lines_tree.heading(column, text=title)
            self.lines_tree.column(
                column,
                width=width,
                anchor=anchor,
                stretch=column == "designation",
            )
        self.lines_tree.pack(fill="both", expand=True)

        receipt_header = ttk.Frame(deliveries_tab)
        receipt_header.pack(fill="x", pady=(10, 5))
        ttk.Label(
            receipt_header,
            text="Réceptions enregistrées",
            font=("Segoe UI Semibold", 10),
        ).pack(side="left")
        ttk.Button(
            receipt_header,
            text="Ajouter une réception…",
            style="Accent.TButton",
            command=self.add_receipt,
        ).pack(side="right")
        ttk.Button(receipt_header, text="Supprimer", command=self.delete_receipt).pack(
            side="right", padx=7
        )
        self.receipts_tree = ttk.Treeview(
            deliveries_tab,
            columns=("date", "reference", "user", "quantity", "notes"),
            show="headings",
            height=5,
            selectmode="browse",
        )
        for column, title, width, anchor in (
            ("date", "Date", 100, "center"),
            ("reference", "N° BL / référence", 180, "w"),
            ("user", "Saisie par", 130, "w"),
            ("quantity", "Unités reçues", 110, "center"),
            ("notes", "Note", 330, "w"),
        ):
            self.receipts_tree.heading(column, text=title)
            self.receipts_tree.column(
                column,
                width=width,
                anchor=anchor,
                stretch=column == "notes",
            )
        self.receipts_tree.pack(fill="both", expand=True)

        comment_actions = ttk.Frame(comments_tab)
        comment_actions.pack(fill="x", pady=(0, 8))
        ttk.Button(
            comment_actions,
            text="Ajouter une note…",
            style="Accent.TButton",
            command=self.add_comment,
        ).pack(side="left")
        ttk.Button(comment_actions, text="Supprimer", command=self.delete_comment).pack(
            side="left", padx=7
        )
        self.comments_tree = ttk.Treeview(
            comments_tab,
            columns=("date", "user", "body"),
            show="headings",
            selectmode="browse",
        )
        for column, title, width in (
            ("date", "Date", 140),
            ("user", "Utilisateur", 140),
            ("body", "Note", 650),
        ):
            self.comments_tree.heading(column, text=title)
            self.comments_tree.column(
                column,
                width=width,
                anchor="w",
                stretch=column == "body",
            )
        self.comments_tree.pack(fill="both", expand=True)

        ttk.Button(content, text="Fermer", command=self.destroy).pack(
            anchor="e", pady=(12, 0)
        )
        self.refresh()
        self.update_idletasks()
        width, height = 1120, 760
        parent_window = parent.winfo_toplevel()
        x, y = centered_window_position(
            parent_window.winfo_rootx(),
            parent_window.winfo_rooty(),
            parent_window.winfo_width(),
            parent_window.winfo_height(),
            width,
            height,
            self.winfo_screenwidth(),
            self.winfo_screenheight(),
        )
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(940, 650)
        self.deiconify()

    def toggle_confirmation(self) -> None:
        order, _ = self.database.get_order(self.order_id)
        confirmed = not bool(order["confirmed_at"])
        expected = None
        if confirmed and self.expected_var.get().strip():
            try:
                expected = date.fromisoformat(self.expected_var.get().strip())
            except ValueError:
                messagebox.showerror(
                    "Confirmation", "Date attendue : AAAA-MM-JJ.", parent=self
                )
                return
        try:
            self.database.mark_order_confirmed(
                self.order_id, confirmed, expected_delivery_date=expected
            )
        except ValueError as exc:
            messagebox.showerror("Confirmation", str(exc), parent=self)
            return
        self.changed = True
        self.refresh()

    def save_expected_date(self) -> None:
        value = self.expected_var.get().strip()
        try:
            expected = date.fromisoformat(value) if value else None
            self.database.update_expected_delivery_date(self.order_id, expected)
        except ValueError as exc:
            messagebox.showerror(
                "Date de livraison",
                str(exc) if str(exc) else "Date attendue : AAAA-MM-JJ.",
                parent=self,
            )
            return
        self.changed = True
        self.refresh()

    def toggle_invoice(self) -> None:
        order, _ = self.database.get_order(self.order_id)
        try:
            self.database.mark_order_invoiced(
                self.order_id, not bool(order["invoiced_at"])
            )
        except ValueError as exc:
            messagebox.showerror("Facturation", str(exc), parent=self)
            return
        self.changed = True
        self.refresh()

    def add_receipt(self) -> None:
        dialog = ReceiptEntryDialog(self, self.database, self.order_id)
        self.wait_window(dialog)
        if dialog.saved:
            self.changed = True
            self.refresh()

    def delete_receipt(self) -> None:
        selected = self.receipts_tree.selection()
        if not selected:
            return
        if not messagebox.askyesno(
            "Supprimer la réception",
            "Supprimer cette réception et recalculer les reliquats ?",
            parent=self,
        ):
            return
        self.database.delete_receipt(int(selected[0]))
        self.changed = True
        self.refresh()

    def add_comment(self) -> None:
        body = simpledialog.askstring(
            "Note interne",
            "Note partagée avec les autres utilisateurs :",
            parent=self,
        )
        if not body:
            return
        self.database.add_order_comment(self.order_id, body)
        self.changed = True
        self.refresh()

    def delete_comment(self) -> None:
        selected = self.comments_tree.selection()
        if not selected:
            return
        if not messagebox.askyesno(
            "Supprimer la note", "Supprimer cette note interne ?", parent=self
        ):
            return
        self.database.delete_order_comment(int(selected[0]))
        self.changed = True
        self.refresh()

    def refresh(self) -> None:
        summary = self.database.receipt_summary(self.order_id)
        order = summary["order"]
        self.status_label.configure(
            text=f"{order['status']}  •  Livraison : {order['delivery_status']}"
        )
        self.expected_var.set(order["expected_delivery_date"] or "")
        self.confirm_button.configure(
            text=(
                "Annuler la confirmation"
                if order["confirmed_at"]
                else "Marquer confirmée"
            )
        )
        self.invoice_button.configure(
            text=(
                "Annuler la facturation" if order["invoiced_at"] else "Marquer facturée"
            )
        )
        self.lines_tree.delete(*self.lines_tree.get_children())
        for line in summary["lines"]:
            self.lines_tree.insert(
                "",
                "end",
                iid=str(line["line_uid"]),
                values=(
                    line["supplier_ref"] or "—",
                    line["designation"],
                    format_number(line["total_units"], 2),
                    format_number(line["received_units"], 2),
                    format_number(line["remaining_units"], 2),
                ),
            )
        self.receipts_tree.delete(*self.receipts_tree.get_children())
        for receipt in summary["receipts"]:
            self.receipts_tree.insert(
                "",
                "end",
                iid=str(receipt["id"]),
                values=(
                    format_timestamp(receipt["receipt_date"]),
                    receipt["reference"] or "—",
                    receipt["received_by"] or "—",
                    format_number(receipt["total_received"], 2),
                    receipt["notes"] or "—",
                ),
            )
        self.comments_tree.delete(*self.comments_tree.get_children())
        for comment in self.database.list_order_comments(self.order_id):
            self.comments_tree.insert(
                "",
                "end",
                iid=str(comment["id"]),
                values=(
                    format_timestamp(comment["created_at"]),
                    comment["author_name"] or "—",
                    comment["body"],
                ),
            )
