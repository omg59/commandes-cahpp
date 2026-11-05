from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from ..database import Database
from ..local_services import attach_document, remove_document, resolve_portable_path
from .common import DOCUMENT_TYPES
from .common import centered_window_position
from .common import open_path


class DocumentPropertiesDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        initial_kind: str = "Confirmation de commande",
        include_in_email: bool = False,
        title: str = "Classer le document",
    ):
        super().__init__(parent)
        self.withdraw()
        self.result_kind: str | None = None
        self.result_include_in_email = include_in_email
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)

        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Type de document").grid(
            row=0, column=0, sticky="w", pady=6
        )
        self.kind_var = tk.StringVar()
        known_kind = initial_kind if initial_kind in DOCUMENT_TYPES[:-1] else "Autre…"
        self.kind_var.set(known_kind)
        kind_box = ttk.Combobox(
            frame,
            textvariable=self.kind_var,
            values=DOCUMENT_TYPES,
            state="readonly",
            width=34,
        )
        kind_box.grid(row=0, column=1, sticky="ew", padx=(12, 0), pady=6)
        kind_box.bind("<<ComboboxSelected>>", lambda event: self._update_custom())

        ttk.Label(frame, text="Type personnalisé").grid(
            row=1, column=0, sticky="w", pady=6
        )
        self.custom_var = tk.StringVar(
            value="" if known_kind != "Autre…" else initial_kind
        )
        self.custom_entry = ttk.Entry(frame, textvariable=self.custom_var, width=36)
        self.custom_entry.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=6)

        self.email_var = tk.BooleanVar(value=include_in_email)
        ttk.Checkbutton(
            frame,
            text="Inclure ce document lors de la préparation du mail",
            variable=self.email_var,
        ).grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(10, 6),
        )
        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Annuler", command=self.destroy).pack(side="left")
        ttk.Button(
            buttons,
            text="Valider",
            style="Accent.TButton",
            command=self.validate,
        ).pack(side="left", padx=(7, 0))
        self._update_custom()
        self._center_on_parent(parent)
        self.deiconify()
        self.lift()
        self.grab_set()
        kind_box.focus_set()

    def _center_on_parent(self, parent: tk.Misc) -> None:
        self.update_idletasks()
        parent.update_idletasks()
        width = max(self.winfo_reqwidth(), self.winfo_width())
        height = max(self.winfo_reqheight(), self.winfo_height())
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

    def _update_custom(self) -> None:
        custom = self.kind_var.get() == "Autre…"
        self.custom_entry.configure(state="normal" if custom else "disabled")
        if custom:
            self.custom_entry.focus_set()

    def validate(self) -> None:
        kind = (
            self.custom_var.get().strip()
            if self.kind_var.get() == "Autre…"
            else self.kind_var.get().strip()
        )
        if not kind:
            messagebox.showerror(
                "Document",
                "Indiquez un type de document.",
                parent=self,
            )
            return
        self.result_kind = kind
        self.result_include_in_email = self.email_var.get()
        self.destroy()


class OrderDocumentsDialog(tk.Toplevel):
    def __init__(self, parent, database: Database, order_id: int):
        super().__init__(parent)
        self.database = database
        self.order_id = order_id
        order, _ = database.get_order(order_id)
        self.title(f"Documents — {order['order_number']}")
        self.transient(parent.winfo_toplevel())
        self.grab_set()

        ttk.Label(
            self,
            text=f"Documents liés à {order['order_number']}",
            font=("Segoe UI Semibold", 14),
        ).pack(anchor="w", padx=18, pady=(16, 3))
        ttk.Label(
            self,
            text=(
                "Les fichiers sont copiés dans l'espace de la commande. "
                "En mode collaboratif, ils sont disponibles sur les deux postes."
            ),
            style="Subtitle.TLabel",
        ).pack(anchor="w", padx=18, pady=(0, 12))

        # Réserver la barre d'actions avant la zone extensible. Ainsi, même
        # lorsque Windows applique une mise à l'échelle élevée, le tableau se
        # réduit en priorité et les boutons restent entièrement visibles.
        actions = ttk.Frame(self)
        actions.pack(side="bottom", fill="x", padx=18, pady=14)
        ttk.Button(
            actions,
            text="Ajouter un document…",
            style="Accent.TButton",
            command=self.add_document,
        ).pack(side="left")
        ttk.Button(
            actions,
            text="Ouvrir",
            command=self.open_selected,
        ).pack(side="right")
        ttk.Button(
            actions,
            text="Supprimer",
            command=self.remove_selected,
        ).pack(side="right", padx=6)
        ttk.Button(
            actions,
            text="Type / mail…",
            command=self.edit_properties,
        ).pack(side="right")

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=18)
        self.tree = ttk.Treeview(
            frame,
            columns=("kind", "name", "email", "state"),
            show="headings",
            selectmode="browse",
        )
        for column, title, width in (
            ("kind", "Type", 145),
            ("name", "Fichier", 360),
            ("email", "Joint au mail", 95),
            ("state", "État", 75),
        ):
            self.tree.heading(column, text=title)
            self.tree.column(
                column,
                width=width,
                stretch=column == "name",
                anchor="w" if column in ("kind", "name") else "center",
            )
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda event: self.open_selected())

        self.refresh()
        self._set_adaptive_geometry(parent.winfo_toplevel())

    def _set_adaptive_geometry(self, parent_window: tk.Misc) -> None:
        """Dimensionner la fenêtre d'après son contenu et l'écran courant."""
        self.update_idletasks()
        minimum_width = max(700, self.winfo_reqwidth())
        minimum_height = max(460, self.winfo_reqheight())
        self.minsize(minimum_width, minimum_height)

        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        width = min(max(800, minimum_width), max(minimum_width, screen_width - 80))
        height = min(
            max(500, minimum_height),
            max(minimum_height, screen_height - 100),
        )

        parent_window.update_idletasks()
        x = parent_window.winfo_rootx() + (parent_window.winfo_width() - width) // 2
        y = parent_window.winfo_rooty() + (parent_window.winfo_height() - height) // 2
        x = max(0, min(x, screen_width - width))
        y = max(0, min(y, screen_height - height))
        self.geometry(f"{width}x{height}+{x}+{y}")

    def selected_attachment_id(self) -> int | None:
        selected = self.tree.selection()
        return int(selected[0]) if selected else None

    def add_files(self, kind: str, include_in_email: bool) -> None:
        paths = filedialog.askopenfilenames(
            parent=self,
            title=f"Ajouter — {kind}",
            filetypes=[
                (
                    "Documents",
                    "*.pdf *.png *.jpg *.jpeg *.doc *.docx *.odt *.rtf "
                    "*.xls *.xlsx *.ods *.csv *.txt *.eml *.msg *.zip",
                ),
                ("Tous les fichiers", "*.*"),
            ],
        )
        if not paths:
            return
        errors = []
        for path in paths:
            try:
                attach_document(
                    self.database,
                    self.order_id,
                    path,
                    kind,
                    include_in_email=include_in_email,
                )
            except OSError as exc:
                errors.append(f"{Path(path).name} : {exc}")
        self.refresh()
        if errors:
            messagebox.showwarning(
                "Documents",
                "Certains fichiers n'ont pas pu être ajoutés :\n" + "\n".join(errors),
                parent=self,
            )

    def add_document(self) -> None:
        dialog = DocumentPropertiesDialog(self)
        self.wait_window(dialog)
        if dialog.result_kind:
            self.add_files(
                dialog.result_kind,
                dialog.result_include_in_email,
            )

    def open_selected(self) -> None:
        attachment_id = self.selected_attachment_id()
        if not attachment_id:
            return
        attachment = self.database.get_order_attachment(attachment_id)
        path = resolve_portable_path(attachment["stored_path"])
        if path.is_file():
            open_path(path)
        else:
            messagebox.showwarning(
                "Document", "Le fichier lié est introuvable.", parent=self
            )

    def toggle_email(self) -> None:
        attachment_id = self.selected_attachment_id()
        if not attachment_id:
            return
        attachment = self.database.get_order_attachment(attachment_id)
        self.database.set_attachment_email(
            attachment_id, not bool(attachment["include_in_email"])
        )
        self.refresh()

    def edit_properties(self) -> None:
        attachment_id = self.selected_attachment_id()
        if not attachment_id:
            messagebox.showinfo("Document", "Sélectionnez un document.", parent=self)
            return
        attachment = self.database.get_order_attachment(attachment_id)
        if attachment is None:
            return
        dialog = DocumentPropertiesDialog(
            self,
            initial_kind=str(attachment["kind"] or ""),
            include_in_email=bool(attachment["include_in_email"]),
            title="Modifier le type du document",
        )
        self.wait_window(dialog)
        if not dialog.result_kind:
            return
        try:
            self.database.update_attachment_properties(
                attachment_id,
                dialog.result_kind,
                dialog.result_include_in_email,
            )
        except ValueError as exc:
            messagebox.showerror("Document", str(exc), parent=self)
            return
        self.refresh()

    def remove_selected(self) -> None:
        attachment_id = self.selected_attachment_id()
        if not attachment_id:
            return
        attachment = self.database.get_order_attachment(attachment_id)
        if not messagebox.askyesno(
            "Supprimer le document",
            f"Retirer et supprimer « {attachment['display_name']} » ?",
            parent=self,
        ):
            return
        remove_document(self.database, attachment_id)
        self.refresh()

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for attachment in self.database.list_order_attachments(self.order_id):
            path = resolve_portable_path(attachment["stored_path"])
            self.tree.insert(
                "",
                "end",
                iid=str(attachment["id"]),
                values=(
                    attachment["kind"],
                    attachment["display_name"],
                    "Oui" if attachment["include_in_email"] else "Non",
                    "Disponible" if path.is_file() else "Absent",
                ),
            )
