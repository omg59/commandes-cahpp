from __future__ import annotations

import threading
import logging
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from .. import __version__
from ..app_logging import log_failure
from ..collaboration import CollaborationError, CollaborationManager
from ..diagnostics import build_diagnostic_report
from ..local_services import (
    MAIL_TEMPLATE_VARIABLES,
    create_complete_backup,
    portable_path,
)
from ..paths import BACKUP_DIR, EXPORT_DIR
from .base import BasePage
from .common import COLORS
from .components import FeedbackButton
from .common import SYNC_INTERVAL_OPTIONS
from .common import format_timestamp
from .common import months_before
from .common import open_path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .app import App

logger = logging.getLogger(__name__)


class SettingsPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._form_baseline: dict[str, object] | None = None
        self.header(
            "Paramètres",
            "Établissement, PDF, e-mails, collaboration et maintenance.",
        )
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)
        identity = ttk.Frame(notebook, style="Surface.TFrame", padding=18)
        pdf = ttk.Frame(notebook, style="Surface.TFrame", padding=18)
        email = ttk.Frame(notebook, style="Surface.TFrame", padding=18)
        backup = ttk.Frame(notebook, style="Surface.TFrame", padding=18)
        collaboration = ttk.Frame(notebook, style="Surface.TFrame", padding=18)
        notebook.add(identity, text="Établissement")
        notebook.add(pdf, text="PDF")
        notebook.add(email, text="E-mail")
        notebook.add(collaboration, text="Collaboration")
        notebook.add(backup, text="Sauvegarde")

        identity_fields = [
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
        ]
        pdf_fields = [
            ("Titre du document PDF", "pdf_title"),
            ("Texte du pied de page PDF", "pdf_footer_text"),
        ]
        email_fields = [
            ("Objet de l'e-mail", "email_subject_template"),
            ("Adresse de composition mail", "mail_compose_url"),
        ]
        fields = identity_fields + pdf_fields + email_fields
        self.vars = {key: tk.StringVar() for _, key in fields}

        def add_fields(surface, definitions) -> int:
            for row, (label, key) in enumerate(definitions):
                ttk.Label(surface, text=label, style="Surface.TLabel").grid(
                    row=row, column=0, sticky="w", pady=7
                )
                ttk.Entry(surface, textvariable=self.vars[key], width=70).grid(
                    row=row, column=1, sticky="ew", padx=(14, 0), pady=7
                )
            surface.columnconfigure(1, weight=1)
            return len(definitions)

        row = add_fields(identity, identity_fields)
        ttk.Label(identity, text="Logo", style="Surface.TLabel").grid(
            row=row, column=0, sticky="w", pady=5
        )
        self.logo_var = tk.StringVar()
        logo_row = ttk.Frame(identity, style="Surface.TFrame")
        logo_row.grid(row=row, column=1, sticky="ew", padx=(14, 0), pady=5)
        ttk.Entry(logo_row, textvariable=self.logo_var).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(logo_row, text="Parcourir", command=self.browse_logo).pack(
            side="left", padx=(7, 0)
        )
        self.identity_save_button = FeedbackButton(
            identity,
            text="Enregistrer",
            command=self.save,
        )
        self.identity_save_button.grid(row=row + 1, column=1, sticky="e", pady=(18, 0))

        row = add_fields(pdf, pdf_fields)
        ttk.Label(
            pdf,
            text="Dossier PDF par défaut",
            style="Surface.TLabel",
        ).grid(row=row, column=0, sticky="w", pady=5)
        self.pdf_directory_var = tk.StringVar()
        pdf_directory_row = ttk.Frame(pdf, style="Surface.TFrame")
        pdf_directory_row.grid(row=row, column=1, sticky="ew", padx=(14, 0), pady=5)
        ttk.Entry(pdf_directory_row, textvariable=self.pdf_directory_var).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(
            pdf_directory_row,
            text="Parcourir",
            command=self.browse_pdf_directory,
        ).pack(side="left", padx=(7, 0))
        row += 1
        self.show_page_number_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            pdf,
            text="Afficher le numéro de page sur le PDF",
            variable=self.show_page_number_var,
        ).grid(row=row, column=1, sticky="w", padx=(14, 0), pady=7)
        self.pdf_save_button = FeedbackButton(
            pdf,
            text="Enregistrer",
            command=self.save,
        )
        self.pdf_save_button.grid(row=row + 1, column=1, sticky="e", pady=(18, 0))

        row = add_fields(email, email_fields)
        ttk.Label(
            email,
            text="Corps de l'e-mail",
            style="Surface.TLabel",
        ).grid(row=row, column=0, sticky="nw", pady=5)
        self.email_body = tk.Text(
            email,
            width=68,
            height=10,
            font=("Segoe UI", 9),
            wrap="word",
            relief="solid",
            bd=1,
        )
        self.email_body.grid(row=row, column=1, sticky="ew", padx=(14, 0), pady=5)
        variables_text = "  •  ".join(
            f"{{{name}}} : {description}"
            for name, description in MAIL_TEMPLATE_VARIABLES.items()
        )
        ttk.Label(
            email,
            text=(
                "Expressions utilisables dans l'objet et le message :\n"
                + variables_text
            ),
            style="Surface.TLabel",
            wraplength=820,
            justify="left",
        ).grid(
            row=row + 1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(14, 0),
        )
        self.email_save_button = FeedbackButton(
            email,
            text="Enregistrer",
            command=self.save,
        )
        self.email_save_button.grid(row=row + 2, column=1, sticky="e", pady=(18, 0))

        ttk.Label(
            backup,
            text="Sauvegarde complète",
            style="Surface.TLabel",
            font=("Segoe UI Semibold", 13),
        ).pack(anchor="w")
        ttk.Label(
            backup,
            text=(
                "L'archive contient la base des commandes, les paramètres, "
                "les fournisseurs et tous les documents liés."
            ),
            style="Surface.TLabel",
            wraplength=700,
        ).pack(anchor="w", pady=(7, 20))
        self.backup_button = FeedbackButton(
            backup,
            text="Exporter une sauvegarde complète",
            command=self.backup,
            success_text="✓ Sauvegarde créée",
        )
        self.backup_button.pack(anchor="w")
        self.backup_status = ttk.Label(
            backup,
            text="",
            style="Success.Surface.TLabel",
            wraplength=760,
        )
        self.backup_status.pack(anchor="w", pady=(10, 0))
        ttk.Separator(backup, orient="horizontal").pack(fill="x", pady=(24, 18))
        maintenance = ttk.Frame(backup, style="Surface.TFrame")
        maintenance.pack(fill="x")
        ttk.Label(
            maintenance,
            text="Rappels et entretien",
            style="Surface.TLabel",
            font=("Segoe UI Semibold", 13),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        ttk.Label(
            maintenance,
            text="Rappeler une sauvegarde après",
            style="Surface.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=6)
        self.backup_reminder_days_var = tk.StringVar(value="14")
        ttk.Combobox(
            maintenance,
            textvariable=self.backup_reminder_days_var,
            values=("7", "14", "30", "60", "90"),
            state="readonly",
            width=8,
        ).grid(row=1, column=1, sticky="w", padx=(14, 6), pady=6)
        ttk.Label(maintenance, text="jours", style="Surface.TLabel").grid(
            row=1, column=2, sticky="w", pady=6
        )
        self.automatic_archive_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            maintenance,
            text="Archiver automatiquement les commandes livrées après",
            variable=self.automatic_archive_var,
        ).grid(row=2, column=0, sticky="w", pady=6)
        self.archive_months_var = tk.StringVar(value="24")
        ttk.Combobox(
            maintenance,
            textvariable=self.archive_months_var,
            values=("6", "12", "18", "24", "36", "60"),
            state="readonly",
            width=8,
        ).grid(row=2, column=1, sticky="w", padx=(14, 6), pady=6)
        ttk.Label(maintenance, text="mois", style="Surface.TLabel").grid(
            row=2, column=2, sticky="w", pady=6
        )
        ttk.Label(
            maintenance,
            text="Alerter si une confirmation manque après",
            style="Surface.TLabel",
        ).grid(row=3, column=0, sticky="w", pady=6)
        self.confirmation_reminder_days_var = tk.StringVar(value="5")
        ttk.Combobox(
            maintenance,
            textvariable=self.confirmation_reminder_days_var,
            values=("2", "3", "5", "7", "10", "14"),
            state="readonly",
            width=8,
        ).grid(row=3, column=1, sticky="w", padx=(14, 6), pady=6)
        ttk.Label(maintenance, text="jours", style="Surface.TLabel").grid(
            row=3, column=2, sticky="w", pady=6
        )
        ttk.Label(
            maintenance,
            text="Alerter sur une livraison sans échéance après",
            style="Surface.TLabel",
        ).grid(row=4, column=0, sticky="w", pady=6)
        self.delivery_reminder_days_var = tk.StringVar(value="14")
        ttk.Combobox(
            maintenance,
            textvariable=self.delivery_reminder_days_var,
            values=("7", "10", "14", "21", "30", "45", "60"),
            state="readonly",
            width=8,
        ).grid(row=4, column=1, sticky="w", padx=(14, 6), pady=6)
        ttk.Label(maintenance, text="jours", style="Surface.TLabel").grid(
            row=4, column=2, sticky="w", pady=6
        )
        maintenance_actions = ttk.Frame(maintenance, style="Surface.TFrame")
        maintenance_actions.grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(14, 0)
        )
        self.maintenance_save_button = FeedbackButton(
            maintenance_actions,
            text="Enregistrer les réglages",
            command=self.save,
        )
        self.maintenance_save_button.pack(side="left")
        ttk.Button(
            maintenance_actions,
            text="Vérifier l'intégrité",
            command=self.check_integrity,
        ).pack(side="left", padx=7)
        ttk.Button(
            maintenance_actions,
            text="Archiver maintenant",
            command=self.run_archive,
        ).pack(side="left")

        ttk.Label(
            collaboration,
            text="Profil et espace partagé",
            style="Surface.TLabel",
            font=("Segoe UI Semibold", 13),
        ).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(
            collaboration,
            text=(
                "Le catalogue reste sur ce poste. Les commandes, corrections "
                "et produits locaux sont synchronisés par fichiers versionnés."
            ),
            style="Surface.TLabel",
            wraplength=780,
        ).grid(
            row=1,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(6, 18),
        )
        ttk.Label(collaboration, text="Nom d'utilisateur", style="Surface.TLabel").grid(
            row=2, column=0, sticky="w", pady=7
        )
        self.user_name_var = tk.StringVar()
        ttk.Entry(collaboration, textvariable=self.user_name_var, width=55).grid(
            row=2, column=1, columnspan=2, sticky="ew", padx=(14, 0), pady=7
        )
        self.collaboration_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            collaboration,
            text="Activer le mode collaboratif",
            variable=self.collaboration_enabled_var,
        ).grid(row=3, column=1, columnspan=2, sticky="w", padx=(14, 0), pady=7)
        ttk.Label(collaboration, text="Dossier partagé", style="Surface.TLabel").grid(
            row=4, column=0, sticky="w", pady=7
        )
        self.shared_path_var = tk.StringVar()
        ttk.Entry(collaboration, textvariable=self.shared_path_var).grid(
            row=4, column=1, sticky="ew", padx=(14, 0), pady=7
        )
        ttk.Button(
            collaboration,
            text="Parcourir",
            command=self.browse_shared_directory,
        ).grid(row=4, column=2, sticky="e", padx=(7, 0), pady=7)
        ttk.Label(
            collaboration,
            text="Synchronisation automatique",
            style="Surface.TLabel",
        ).grid(row=5, column=0, sticky="w", pady=7)
        self.sync_interval_var = tk.StringVar(value="1 minute")
        ttk.Combobox(
            collaboration,
            textvariable=self.sync_interval_var,
            values=tuple(SYNC_INTERVAL_OPTIONS),
            state="readonly",
            width=20,
        ).grid(row=5, column=1, sticky="w", padx=(14, 0), pady=7)
        self.pause_sync_editing_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            collaboration,
            text=(
                "Mettre la synchronisation en pause pendant une saisie non enregistrée"
            ),
            variable=self.pause_sync_editing_var,
        ).grid(
            row=6,
            column=1,
            columnspan=2,
            sticky="w",
            padx=(14, 0),
            pady=7,
        )
        collaboration.columnconfigure(1, weight=1)
        collab_actions = ttk.Frame(collaboration, style="Surface.TFrame")
        collab_actions.grid(
            row=7, column=1, columnspan=2, sticky="w", padx=(14, 0), pady=(12, 0)
        )
        ttk.Button(
            collab_actions,
            text="Tester l'accès",
            command=self.test_shared_directory,
        ).pack(side="left")
        self.collaboration_save_button = FeedbackButton(
            collab_actions,
            text="Enregistrer",
            command=self.save,
        )
        self.collaboration_save_button.pack(side="left", padx=7)
        ttk.Button(
            collab_actions,
            text="Synchroniser maintenant",
            style="Accent.TButton",
            command=self.sync_now,
        ).pack(side="left")
        ttk.Button(
            collab_actions,
            text="Ouvrir le dossier",
            command=self.open_shared_directory,
        ).pack(side="left", padx=7)
        ttk.Button(
            collab_actions,
            text="Diagnostic",
            command=self.open_diagnostic,
        ).pack(side="left")
        self.collaboration_status = ttk.Label(
            collaboration,
            text="",
            style="Surface.TLabel",
            wraplength=780,
            justify="left",
        )
        self.collaboration_status.grid(
            row=8,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(18, 0),
        )

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
            self.logo_var.set(portable_path(path))

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

    def browse_shared_directory(self) -> None:
        current = self.shared_path_var.get().strip()
        path = filedialog.askdirectory(
            parent=self,
            title="Choisir le dossier partagé",
            initialdir=(
                current if current and Path(current).is_dir() else str(Path.home())
            ),
        )
        if path:
            self.shared_path_var.set(path)
            self.collaboration_enabled_var.set(True)

    def test_shared_directory(self) -> None:
        path = self.shared_path_var.get().strip()
        if not path:
            messagebox.showinfo(
                "Collaboration",
                "Sélectionnez d'abord un dossier partagé.",
                parent=self,
            )
            return
        try:
            result = CollaborationManager.test_path(path)
        except OSError as exc:
            self.collaboration_status.configure(
                text=f"Accès impossible : {exc}", foreground=COLORS["danger"]
            )
            return
        lines = [
            f"Lecture : {'OK' if result.readable else 'Échec'}",
            f"Écriture : {'OK' if result.writable else 'Échec'}",
            ("Renommage sécurisé : " + ("OK" if result.atomic_rename else "Échec")),
            (
                "Espace existant : "
                + (
                    f"oui ({result.workspace_id})"
                    if result.workspace_found
                    else "non — il sera créé à l'enregistrement"
                )
            ),
        ]
        self.collaboration_status.configure(
            text="\n".join(lines),
            foreground=COLORS["success"] if result.ok else COLORS["danger"],
        )

    def open_shared_directory(self) -> None:
        path = Path(self.shared_path_var.get().strip())
        if path.is_dir():
            open_path(path)
        else:
            messagebox.showinfo(
                "Collaboration",
                "Le dossier partagé est indisponible.",
                parent=self,
            )

    def sync_now(self) -> None:
        if self.save():
            self.app.sync_collaboration(show_errors=True)

    def open_diagnostic(self) -> None:
        DiagnosticDialog(self, self.app)

    def save(self) -> bool:
        user_name = self.user_name_var.get().strip()
        if not user_name:
            messagebox.showerror(
                "Profil utilisateur",
                "Le nom d'utilisateur est obligatoire.",
                parent=self,
            )
            return False
        shared_path = self.shared_path_var.get().strip()
        if self.collaboration_enabled_var.get() and not shared_path:
            messagebox.showerror(
                "Collaboration",
                "Sélectionnez le dossier partagé.",
                parent=self,
            )
            return False
        previous = self.database.get_settings()
        values = {key: variable.get() for key, variable in self.vars.items()}
        values["logo_path"] = self.logo_var.get()
        values["pdf_default_directory"] = self.pdf_directory_var.get()
        values["email_body_template"] = self.email_body.get("1.0", "end").strip()
        values["pdf_show_page_number"] = "1" if self.show_page_number_var.get() else "0"
        values["user_name"] = user_name
        values["collaboration_enabled"] = (
            "1" if self.collaboration_enabled_var.get() else "0"
        )
        values["shared_workspace_path"] = shared_path
        values["sync_interval_seconds"] = SYNC_INTERVAL_OPTIONS.get(
            self.sync_interval_var.get(), "60"
        )
        values["pause_sync_while_editing"] = (
            "1" if self.pause_sync_editing_var.get() else "0"
        )
        values["backup_reminder_days"] = self.backup_reminder_days_var.get()
        values["automatic_archive_enabled"] = (
            "1" if self.automatic_archive_var.get() else "0"
        )
        values["archive_after_months"] = self.archive_months_var.get()
        values["confirmation_reminder_days"] = self.confirmation_reminder_days_var.get()
        values["delivery_reminder_days"] = self.delivery_reminder_days_var.get()
        self.database.save_settings(values)
        self._form_baseline = self._current_form_values()
        collaboration_changed = any(
            previous.get(key, "") != values.get(key, "")
            for key in (
                "user_name",
                "collaboration_enabled",
                "shared_workspace_path",
            )
        )
        if collaboration_changed:
            try:
                self.app.reconfigure_collaboration()
            except (OSError, CollaborationError) as exc:
                messagebox.showerror(
                    "Collaboration",
                    f"Les paramètres sont enregistrés, mais l'accès a échoué :\n{exc}",
                    parent=self,
                )
                return False
        elif self.app.collaboration:
            self.app.sync_team_data()
        self.app.reschedule_periodic_collaboration()
        return True

    def _current_form_values(self) -> dict[str, object]:
        values: dict[str, object] = {
            key: variable.get() for key, variable in self.vars.items()
        }
        values.update(
            {
                "logo_path": self.logo_var.get(),
                "pdf_default_directory": self.pdf_directory_var.get(),
                "email_body_template": self.email_body.get("1.0", "end").strip(),
                "pdf_show_page_number": self.show_page_number_var.get(),
                "user_name": self.user_name_var.get(),
                "collaboration_enabled": (self.collaboration_enabled_var.get()),
                "shared_workspace_path": self.shared_path_var.get(),
                "sync_interval": self.sync_interval_var.get(),
                "pause_sync_while_editing": (self.pause_sync_editing_var.get()),
                "backup_reminder_days": self.backup_reminder_days_var.get(),
                "automatic_archive_enabled": self.automatic_archive_var.get(),
                "archive_after_months": self.archive_months_var.get(),
                "confirmation_reminder_days": (
                    self.confirmation_reminder_days_var.get()
                ),
                "delivery_reminder_days": self.delivery_reminder_days_var.get(),
            }
        )
        return values

    def has_unsaved_changes(self) -> bool:
        return (
            self._form_baseline is not None
            and self._current_form_values() != self._form_baseline
        )

    def backup(self) -> bool:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        selected = filedialog.asksaveasfilename(
            parent=self,
            title="Exporter la sauvegarde complète",
            initialdir=str(BACKUP_DIR),
            initialfile=f"commandes-cahpp-{timestamp}.zip",
            defaultextension=".zip",
            filetypes=[("Archive ZIP", "*.zip")],
        )
        if not selected:
            return False
        destination = create_complete_backup(self.database, selected)
        self.database.save_settings(
            {
                "last_backup_at": datetime.now().isoformat(timespec="seconds"),
                "last_backup_path": str(destination),
            }
        )
        self.backup_status.configure(
            text=f"Sauvegarde complète créée : {destination}",
            foreground=COLORS["success"],
        )
        self.app.refresh_pages()
        return True

    def check_integrity(self) -> None:
        ok, detail = self.database.quick_integrity_check()
        checked_at = datetime.now().isoformat(timespec="seconds")
        self.database.save_settings(
            {
                "last_integrity_check_at": checked_at,
                "last_integrity_check_result": "OK" if ok else detail,
            }
        )
        self.backup_status.configure(
            text=(
                "Contrôle d'intégrité réussi."
                if ok
                else "Anomalie détectée : " + detail
            ),
            foreground=COLORS["success"] if ok else COLORS["danger"],
        )
        self.app.refresh_pages()

    def run_archive(self) -> None:
        try:
            months = int(self.archive_months_var.get())
        except ValueError:
            months = 24
        before = months_before(date.today(), max(1, months))
        if not messagebox.askyesno(
            "Archivage",
            (
                "Archiver les commandes marquées comme livrées datant "
                f"d'avant le {before:%d/%m/%Y} ?\n\n"
                "Elles resteront consultables en cochant « Inclure les "
                "archives » dans l'historique."
            ),
            parent=self,
        ):
            return
        archived = self.database.archive_old_orders(before)
        self.database.save_settings(
            {"last_maintenance_at": datetime.now().isoformat(timespec="seconds")}
        )
        self.backup_status.configure(
            text=f"{len(archived)} commande(s) archivée(s).",
            foreground=COLORS["success"],
        )
        self.app.refresh_pages()
        if archived and self.app.collaboration:
            self.app.sync_collaboration()

    def refresh(self) -> None:
        if self.has_unsaved_changes():
            self._valid = True
            return
        settings = self.database.get_settings()
        for key, variable in self.vars.items():
            variable.set(settings.get(key, ""))
        self.logo_var.set(settings.get("logo_path", ""))
        self.pdf_directory_var.set(settings.get("pdf_default_directory", ""))
        self.email_body.delete("1.0", "end")
        self.email_body.insert("1.0", settings.get("email_body_template", ""))
        self.show_page_number_var.set(settings.get("pdf_show_page_number", "1") != "0")
        self.user_name_var.set(settings.get("user_name", ""))
        self.shared_path_var.set(settings.get("shared_workspace_path", ""))
        self.collaboration_enabled_var.set(
            settings.get("collaboration_enabled", "0") == "1"
        )
        interval_seconds = settings.get("sync_interval_seconds", "60")
        interval_label = next(
            (
                label
                for label, seconds in SYNC_INTERVAL_OPTIONS.items()
                if seconds == interval_seconds
            ),
            "1 minute",
        )
        self.sync_interval_var.set(interval_label)
        self.pause_sync_editing_var.set(
            settings.get("pause_sync_while_editing", "1") != "0"
        )
        self.backup_reminder_days_var.set(settings.get("backup_reminder_days", "14"))
        self.automatic_archive_var.set(
            settings.get("automatic_archive_enabled", "0") == "1"
        )
        self.archive_months_var.set(settings.get("archive_after_months", "24"))
        self.confirmation_reminder_days_var.set(
            settings.get("confirmation_reminder_days", "5")
        )
        self.delivery_reminder_days_var.set(
            settings.get("delivery_reminder_days", "14")
        )
        last_backup = settings.get("last_backup_at", "")
        last_integrity = settings.get("last_integrity_check_at", "")
        if not self.backup_status.cget("text"):
            self.backup_status.configure(
                text=(
                    "Dernière sauvegarde : "
                    f"{format_timestamp(last_backup)}  •  "
                    "Dernier contrôle : "
                    f"{format_timestamp(last_integrity)}"
                ),
                foreground=COLORS["muted"],
            )
        if self.app.collaboration:
            last_sync = settings.get("collaboration_last_sync_at", "")
            catalogue = settings.get("collaboration_catalog_version", "")
            pending = len(self.database.pending_order_ids())
            last_result = self.app.last_sync_result or {}
            order_result = dict(last_result.get("orders") or {})
            error_text = (
                f"\nDernière erreur : {self.app.last_sync_error}"
                if self.app.last_sync_error
                else ""
            )
            self.collaboration_status.configure(
                text=(
                    f"Espace : {self.app.collaboration.workspace_id}\n"
                    f"Dernière synchronisation : "
                    f"{format_timestamp(last_sync)}\n"
                    f"Catalogue partagé : {catalogue or 'non publié'}\n"
                    f"Commandes locales en attente : {pending}\n"
                    "Dernier échange : "
                    f"{order_result.get('imported', 0)} reçue(s), "
                    f"{order_result.get('published', 0)} envoyée(s), "
                    f"{order_result.get('conflicts', 0)} verrou/conflit"
                    f"{error_text}"
                ),
                foreground=(
                    COLORS["warning"]
                    if pending or self.app.last_sync_error
                    else COLORS["success"]
                ),
            )
        elif self.collaboration_enabled_var.get():
            self.collaboration_status.configure(
                text="Espace partagé actuellement indisponible.",
                foreground=COLORS["warning"],
            )
        else:
            self.collaboration_status.configure(
                text="Mode local.", foreground=COLORS["muted"]
            )
        self._form_baseline = self._current_form_values()
        self._valid = True


class DiagnosticDialog(tk.Toplevel):
    def __init__(self, parent, app: App):
        super().__init__(parent)
        self.app = app
        self.report = ""
        self._busy = False
        self.title(f"Diagnostic — Commandes CAHPP {__version__}")
        self.geometry("900x650")
        self.minsize(700, 480)
        self.transient(parent.winfo_toplevel())
        self.grab_set()

        content = ttk.Frame(self, padding=16)
        content.pack(fill="both", expand=True)
        ttk.Label(
            content,
            text="Diagnostic de l'application",
            font=("Segoe UI Semibold", 14),
        ).pack(anchor="w")
        ttk.Label(
            content,
            text=(
                "Contrôle la base locale, l'espace partagé, le catalogue et "
                "les commandes encore en attente."
            ),
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 10))

        repair_actions = ttk.Frame(content)
        repair_actions.pack(fill="x", pady=(0, 10))
        self.repair_button = ttk.Button(
            repair_actions,
            text="Reconstruire l'index",
            command=self.repair_index,
        )
        self.repair_button.pack(side="left")
        ttk.Label(
            repair_actions,
            text="Recrée la recherche locale à partir des articles, puis vérifie son fonctionnement.",
            wraplength=440,
            style="Subtitle.TLabel",
        ).pack(side="left", padx=10)

        report_frame = ttk.Frame(content)
        self.text = tk.Text(
            report_frame,
            wrap="none",
            font=("Consolas", 9),
            relief="solid",
            bd=1,
        )
        vertical = ttk.Scrollbar(
            report_frame, orient="vertical", command=self.text.yview
        )
        horizontal = ttk.Scrollbar(
            report_frame, orient="horizontal", command=self.text.xview
        )
        self.text.configure(
            yscrollcommand=vertical.set,
            xscrollcommand=horizontal.set,
        )
        self.text.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        report_frame.rowconfigure(0, weight=1)
        report_frame.columnconfigure(0, weight=1)

        footer = ttk.Frame(content)
        footer.pack(side="bottom", fill="x")
        self.status = ttk.Label(
            footer, text="", style="Subtitle.TLabel", wraplength=620
        )
        self.status.pack(anchor="w", pady=(8, 0))
        actions = ttk.Frame(footer)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(actions, text="Fermer", command=self.destroy).pack(side="right")
        self.export_button = ttk.Button(
            actions,
            text="Exporter le rapport",
            command=self.export_report,
            state="disabled",
        )
        self.export_button.pack(side="right", padx=6)
        self.copy_button = ttk.Button(
            actions,
            text="Copier",
            command=self.copy_report,
            state="disabled",
        )
        self.copy_button.pack(side="right")
        self.refresh_button = ttk.Button(
            actions,
            text="Relancer",
            style="Accent.TButton",
            command=self.run_diagnostic,
        )
        self.refresh_button.pack(side="right", padx=6)
        report_frame.pack(fill="both", expand=True)
        self.run_diagnostic()

    def run_diagnostic(self) -> None:
        self._run_worker(repair=False)

    def repair_index(self) -> None:
        self._run_worker(repair=True)

    def _run_worker(self, *, repair: bool) -> None:
        if self._busy:
            return
        self._busy = True
        self.refresh_button.configure(state="disabled")
        self.repair_button.configure(state="disabled")
        self.copy_button.configure(state="disabled")
        self.export_button.configure(state="disabled")
        pending = "Reconstruction en cours…" if repair else "Analyse en cours…"
        self.status.configure(text=pending)
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", pending)
        self.text.configure(state="disabled")

        def worker() -> None:
            success = None
            try:
                if repair:
                    success = self.app.database.rebuild_search(manual=True)
                report = build_diagnostic_report(
                    self.app.database,
                    self.app.collaboration,
                    __version__,
                    self.app.last_sync_result,
                    self.app.last_sync_error,
                )
            except Exception as exc:
                log_failure(logger, "diagnostic_worker_echec", exc)
                report = (
                    "Le diagnostic n'a pas pu être terminé.\n"
                    f"Erreur technique : {type(exc).__name__}, "
                    f"{getattr(exc, 'sqlite_errorname', 'sans code SQLite')}.\n"
                    "Consultez le journal technique pour la pile d'appels."
                )
                if repair:
                    success = False
            self.app.post_ui(lambda: self.show_report(report, repair_success=success))

        threading.Thread(target=worker, daemon=True).start()

    def show_report(self, report: str, *, repair_success: bool | None = None) -> None:
        if not self.winfo_exists():
            return
        self.report = report
        self._busy = False
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", report)
        self.text.configure(state="disabled")
        self.refresh_button.configure(state="normal")
        self.repair_button.configure(state="normal")
        self.copy_button.configure(state="normal")
        self.export_button.configure(state="normal")
        status = "Diagnostic terminé."
        if repair_success is True:
            status = "Index reconstruit et testé. Relancez votre recherche."
        elif repair_success is False:
            status = "Échec de reconstruction. Exportez le rapport."
        self.status.configure(text=status)

    def copy_report(self) -> None:
        if not self.report:
            return
        self.clipboard_clear()
        self.clipboard_append(self.report)
        self.status.configure(text="Rapport copié.")

    def export_report(self) -> None:
        if not self.report:
            return
        selected = filedialog.asksaveasfilename(
            parent=self,
            title="Exporter le diagnostic",
            initialdir=str(BACKUP_DIR),
            initialfile=(
                f"diagnostic-commandes-cahpp-{datetime.now():%Y%m%d-%H%M%S}.txt"
            ),
            defaultextension=".txt",
            filetypes=[("Fichier texte", "*.txt")],
        )
        if not selected:
            return
        try:
            Path(selected).write_text(self.report, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror(
                "Diagnostic",
                f"Le rapport n'a pas pu être enregistré :\n{exc}",
                parent=self,
            )
            return
        self.status.configure(text=f"Rapport enregistré : {selected}")
