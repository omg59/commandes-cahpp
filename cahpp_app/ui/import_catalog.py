from __future__ import annotations

import queue
import threading
from contextlib import nullcontext
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from ..app_logging import log_failure
from ..catalog_importer import CatalogImporter, ImportOptions, ImportResult
from ..collaboration import CollaborationError
from ..local_services import create_complete_backup
from ..paths import BACKUP_DIR
from .base import BasePage
from .common import COLORS
from .common import format_number
from .common import format_price
import logging

logger = logging.getLogger(__name__)


class PriceChangesDialog(tk.Toplevel):
    def __init__(self, parent, rows):
        super().__init__(parent)
        self.title("Changements sur les articles déjà commandés")
        self.geometry("1050x520")
        self.minsize(800, 380)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        ttk.Label(
            self,
            text=f"{len(rows)} article(s) déjà commandé(s) ont changé",
            font=("Segoe UI Semibold", 14),
        ).pack(anchor="w", padx=18, pady=(16, 3))
        ttk.Label(
            self,
            text=(
                "Les anciennes commandes restent inchangées ; les nouvelles "
                "utiliseront les valeurs du catalogue importé."
            ),
            style="Subtitle.TLabel",
        ).pack(anchor="w", padx=18, pady=(0, 12))
        tree = ttk.Treeview(
            self,
            columns=(
                "supplier",
                "reference",
                "designation",
                "old_price",
                "new_price",
                "old_pack",
                "new_pack",
            ),
            show="headings",
        )
        for column, title, width in (
            ("supplier", "Fournisseur", 145),
            ("reference", "Référence", 95),
            ("designation", "Désignation", 330),
            ("old_price", "Ancien PU", 90),
            ("new_price", "Nouveau PU", 90),
            ("old_pack", "Ancien cond.", 85),
            ("new_pack", "Nouveau cond.", 85),
        ):
            tree.heading(column, text=title)
            tree.column(
                column,
                width=width,
                stretch=column == "designation",
                anchor="w" if column in ("supplier", "designation") else "center",
            )
        for row in rows:
            tree.insert(
                "",
                "end",
                values=(
                    row["supplier_name"],
                    row["supplier_ref"],
                    row["designation"],
                    format_price(row["old_price"]),
                    format_price(row["new_price"]),
                    format_number(row["old_pack"]),
                    format_number(row["new_pack"]),
                ),
            )
        tree.pack(fill="both", expand=True, padx=18)
        ttk.Button(self, text="Fermer", command=self.destroy).pack(
            anchor="e", padx=18, pady=14
        )


class ImportPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header(
            "Mise à jour CAHPP",
            "Catalogue complet ou évolutions mensuelles : le format est détecté et les changements sont historisés.",
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
        self.progress = ttk.Progressbar(progress_box, mode="determinate", maximum=100)
        self.progress.pack(fill="x")
        self.status_label = ttk.Label(
            progress_box,
            text="Sélectionnez un catalogue complet ou un fichier d'évolutions mensuelles.",
            style="Subtitle.TLabel",
        )
        self.status_label.pack(anchor="w", pady=(5, 0))

        history_header = ttk.Frame(self)
        history_header.pack(fill="x", pady=(22, 8))
        ttk.Label(
            history_header,
            text="Historique des imports",
            font=("Segoe UI Semibold", 11),
        ).pack(side="left")
        ttk.Button(
            history_header,
            text="Voir les changements déjà commandés",
            command=self.show_selected_changes,
        ).pack(side="right")
        self.tree = ttk.Treeview(
            self,
            columns=("date", "file", "mode", "rows", "added", "updated", "missing"),
            show="headings",
            height=10,
        )
        for column, title, width in (
            ("date", "Date", 135),
            ("file", "Fichier", 320),
            ("mode", "Type / mois", 150),
            ("rows", "Articles", 90),
            ("added", "Ajoutés", 75),
            ("updated", "Modifiés", 75),
            ("missing", "Retirés", 75),
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
        self.import_running = False
        self._shared_manifest: dict[str, object] | None = None
        self._confirmation = threading.Event()
        self._cancelled = threading.Event()
        self._poll_id = None
        self._import_options = ImportOptions()
        self._last_import_backup = ""

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
        self._shared_manifest = None
        self._start_worker(path, None)

    def start_shared_import(self, manifest: dict[str, object]) -> None:
        if not self.app.collaboration:
            return
        self._shared_manifest = dict(manifest)
        self.path_var.set(f"Catalogue partagé : {manifest.get('version', '')}")
        self._start_worker(None, self._shared_manifest)

    def _start_worker(
        self,
        path: Path | None,
        shared_manifest: dict[str, object] | None,
    ) -> None:
        if self.import_running:
            return
        self.import_running = True
        self._confirmation.clear()
        self._cancelled.clear()
        self._import_options = ImportOptions()
        self._last_import_backup = ""
        self.import_button.configure(state="disabled")
        self.progress["value"] = 0
        self.worker = threading.Thread(
            target=self._run_import,
            args=(path, shared_manifest),
            daemon=True,
        )
        self.worker.start()
        self._poll_id = self.after(100, self._poll_messages)

    def _run_import(
        self,
        path: Path | None,
        shared_manifest: dict[str, object] | None,
    ) -> None:
        try:
            manager = self.app.collaboration
            if shared_manifest is not None:
                if not manager:
                    raise CollaborationError("Le mode collaboratif n'est plus actif.")
                self.messages.put(
                    ("progress", 0, "Vérification du catalogue partagé...")
                )
                path = manager.catalog_source(shared_manifest)
            if path is None:
                raise FileNotFoundError("Catalogue introuvable")
            importer = CatalogImporter(self.database)
            self.messages.put(
                ("progress", 2, "Analyse du format et contrôle du fichier…")
            )
            preview = importer.inspect_file(path)
            if not preview.already_imported and (
                shared_manifest is None or preview.confirmations
            ):
                self.messages.put(("confirm", preview))
                self._confirmation.wait()
            if self._cancelled.is_set() or self.app._closing:
                self.messages.put(("cancelled",))
                return

            def progress(current, total, message):
                if self._cancelled.is_set() or self.app._closing:
                    raise ValueError(
                        "Import annulé à la fermeture ; transaction non validée."
                    )
                self.messages.put(("progress", current, message))

            context = (
                manager.acquire_lock("systeme", "catalogue", ttl_seconds=600)
                if manager and shared_manifest is None
                else nullcontext()
            )
            with context as handle:
                if handle:
                    handle.refresh()
                if (
                    manager
                    and shared_manifest is None
                    and preview.mode == "delta"
                    and manager.pending_catalog()
                ):
                    raise CollaborationError(
                        "Un catalogue partagé plus récent est disponible. Appliquez-le avant d'importer les évolutions mensuelles."
                    )
                if not preview.already_imported:
                    self.messages.put(
                        ("progress", 4, "Sauvegarde automatique avant import…")
                    )
                    self._backup_before_import()
                if self._cancelled.is_set() or self.app._closing:
                    self.messages.put(("cancelled",))
                    return
                if handle:
                    handle.refresh()
                result = importer.import_file(
                    path,
                    progress=progress,
                    options=self._import_options,
                    preview=preview,
                )
                publication, publication_error = None, ""
                try:
                    if shared_manifest is not None and manager:
                        manager.mark_catalog_applied(shared_manifest)
                        publication = shared_manifest
                    elif manager:
                        self.messages.put(
                            (
                                "progress",
                                99,
                                "Publication du catalogue complet sur le partage…",
                            )
                        )
                        publication = manager.publish_catalog(path, result, lock=handle)
                except (OSError, CollaborationError, ValueError) as exc:
                    log_failure(logger, "publication_catalogue_echec", exc)
                    publication_error = str(exc)
            self.messages.put(("done", result, publication, publication_error))
        except Exception as exc:
            log_failure(logger, "import_catalogue_echec", exc)
            self.messages.put(("error", str(exc)))

    def _backup_before_import(self) -> None:
        destination = BACKUP_DIR / (
            "avant-import-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".zip"
        )
        temporary = destination.with_name("." + destination.name)
        try:
            create_complete_backup(self.database, temporary)
            temporary.replace(destination)
        except Exception:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as cleanup_error:
                log_failure(logger, "sauvegarde_import_nettoyage_echec", cleanup_error)
            raise
        self._last_import_backup = str(destination)
        self.database.save_settings(
            {
                "last_backup_at": datetime.now().isoformat(timespec="seconds"),
                "last_backup_path": str(destination),
            }
        )

    def _poll_messages(self) -> None:
        self._poll_id = None
        try:
            while True:
                message = self.messages.get_nowait()
                if message[0] == "progress":
                    self.progress["value"] = message[1]
                    self.status_label.configure(text=message[2])
                elif message[0] == "confirm":
                    preview = message[1]
                    label = {
                        "full": "Catalogue complet",
                        "delta": "Évolutions mensuelles",
                        "snapshot": "Catalogue partagé complet",
                    }[preview.mode]
                    details = f"Format détecté : {label}\n{preview.row_count:,} lignes".replace(
                        ",", " "
                    )
                    if preview.period:
                        details += f"\nMois : {preview.period}"
                    if preview.warnings:
                        details += "\n\n" + "\n\n".join(preview.warnings)
                    approved = messagebox.askyesno(
                        "Vérifier l'import CAHPP",
                        details
                        + "\n\nUne sauvegarde complète sera créée avant l'import.\nAppliquer cet import ?",
                        icon="warning" if preview.confirmations else "question",
                        parent=self,
                    )
                    if approved:
                        self._import_options = ImportOptions(
                            confirm_baseline="baseline" in preview.confirmations,
                            allow_revision="revision" in preview.confirmations,
                            confirm_full_replacement="replacement"
                            in preview.confirmations,
                            confirm_snapshot_replacement="snapshot_replacement"
                            in preview.confirmations,
                        )
                    else:
                        self._cancelled.set()
                    self._confirmation.set()
                elif message[0] == "cancelled":
                    self.import_running = False
                    self.import_button.configure(state="normal")
                    self.status_label.configure(
                        text="Import annulé. Le catalogue n'a pas été modifié."
                    )
                    return
                elif message[0] == "done":
                    try:
                        self._import_done(message[1], message[2], message[3])
                    finally:
                        self.import_running = False
                    return
                elif message[0] == "error":
                    self.import_button.configure(state="normal")
                    self.status_label.configure(text="Échec de l'import.")
                    messagebox.showerror("Import CAHPP", message[1], parent=self)
                    self.import_running = False
                    return
        except queue.Empty:
            pass
        if self.import_running and not self.app._closing:
            self._poll_id = self.after(100, self._poll_messages)

    def _import_done(
        self,
        result: ImportResult,
        publication: dict[str, object] | None = None,
        publication_error: str = "",
    ) -> None:
        self.import_button.configure(state="normal")
        self.progress["value"] = 100
        if publication_error:
            self.status_label.configure(
                text="Catalogue local mis à jour ; publication à réessayer."
            )
            messagebox.showwarning(
                "Publication du catalogue incomplète",
                "Le catalogue de ce poste est mis à jour, mais la diffusion sur le partage n'a pas été terminée. "
                "Relancez l'import du même fichier pour réessayer sans appliquer ses changements deux fois.\n\n"
                + publication_error,
                parent=self,
            )
        if result.already_imported:
            self.status_label.configure(text="Ce fichier avait déjà été importé.")
            messagebox.showinfo(
                "Import CAHPP",
                "Ce fichier est identique à un catalogue déjà importé.",
                parent=self,
            )
        else:
            self.status_label.configure(
                text=(
                    "Catalogue mis à jour et synchronisé."
                    if publication
                    else "Catalogue mis à jour."
                )
            )
            ordered_changes = self.database.ordered_changes_for_import(result.import_id)
            details = (
                f"{result.row_count:,} articles lus\n"
                f"{result.added_count:,} ajoutés\n"
                f"{result.updated_count:,} modifiés\n"
                f"{result.deactivated_count:,} retirés du catalogue actif\n"
                f"{result.review_count:,} articles à vérifier dans Catalogue\n"
                f"{len(ordered_changes):,} article(s) déjà commandé(s) modifié(s)"
            ).replace(",", " ")
            if self._last_import_backup:
                details += (
                    "\n\nSauvegarde avant import : "
                    + Path(self._last_import_backup).name
                )
            messagebox.showinfo("Import CAHPP terminé", details, parent=self)
            if ordered_changes:
                dialog = PriceChangesDialog(self, ordered_changes)
                self.wait_window(dialog)
        if publication_error:
            self.status_label.configure(
                text="Catalogue local mis à jour ; publication à réessayer."
            )
        self.app.refresh_pages()
        self.refresh()
        if self.app.collaboration:
            self.app.sync_collaboration()

    def show_selected_changes(self) -> None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo(
                "Changements",
                "Sélectionnez un import dans l'historique.",
                parent=self,
            )
            return
        rows = self.database.ordered_changes_for_import(int(selected[0]))
        if not rows:
            messagebox.showinfo(
                "Changements",
                "Aucun changement de prix ou de conditionnement ne concerne "
                "un article déjà commandé pour cet import.",
                parent=self,
            )
            return
        dialog = PriceChangesDialog(self, rows)
        self.wait_window(dialog)

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
                    {"full": "Complet", "delta": "Mensuel", "snapshot": "Partagé"}.get(
                        item["mode"], item["mode"]
                    )
                    + (" " + item["period"] if item["period"] else ""),
                    format_number(item["row_count"]),
                    format_number(item["added_count"]),
                    format_number(item["updated_count"]),
                    format_number(item["deactivated_count"] or item["missing_count"]),
                ),
            )
        self._valid = True

    def shutdown(self) -> None:
        self._cancelled.set()
        self._confirmation.set()
        if self._poll_id:
            self.after_cancel(self._poll_id)
            self._poll_id = None
