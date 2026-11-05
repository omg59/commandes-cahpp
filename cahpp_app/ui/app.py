from __future__ import annotations

import os
import subprocess
import threading
import queue
import tkinter as tk
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from .. import __version__
from ..app_logging import log_failure
from ..collaboration import (
    CollaborationError,
    CollaborationManager,
    ResourceLock,
    ResourceLockedError,
)
from ..database import Database
from ..local_services import configure_shared_workspace
from ..paths import ROOT_DIR
from .common import COLORS
from .catalog import CatalogPage
from .dashboard import DashboardPage
from .import_catalog import ImportPage
from .order import OrderPage
from .history import OrdersPage
from .settings import SettingsPage
from .statistics import StatisticsPage
from .suggestions import SuggestionsPage
from .suppliers import SuppliersPage
from .common import months_before
from .common import open_path
from .common import timestamp_is_due
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import BasePage
import logging

logger = logging.getLogger(__name__)


class App(ttk.Frame):
    def __init__(self, root: tk.Tk, database: Database):
        super().__init__(root)
        self.root = root
        self.database = database
        self._closing = False
        self._ui_events = queue.SimpleQueue()
        self._ui_poll_id = None
        self._heartbeat_running = False
        self.root.title("Commandes CAHPP")
        self._configure_window_icon()
        self._syncing = False
        self._catalog_prompted_hash = ""
        self._installer_prompted_version = ""
        self._periodic_started = False
        self._periodic_after_id: str | None = None
        self.last_sync_result: dict[str, object] | None = None
        self.last_sync_error = ""
        self.collaboration: CollaborationManager | None = None
        self._initialize_user_and_collaboration()
        self.root.geometry("1450x820")
        self.root.minsize(1420, 680)
        self._configure_styles()
        self.pack(fill="both", expand=True)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.sidebar = tk.Frame(self, bg=COLORS["nav"], width=210)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.content = tk.Frame(self, bg=COLORS["background"])
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.rowconfigure(0, weight=1)
        self.content.columnconfigure(0, weight=1)

        tk.Label(
            self.sidebar,
            text="COMMANDES\nCAHPP",
            bg=COLORS["nav"],
            fg="white",
            font=("Segoe UI Semibold", 17),
            justify="left",
            padx=20,
            pady=22,
        ).pack(fill="x")

        self.pages: dict[str, BasePage] = {}
        self.nav_buttons: dict[str, tk.Button] = {}
        self.nav_indicators: dict[str, tk.Frame] = {}
        self.nav_rows: dict[str, tk.Frame] = {}
        self.active_page = ""
        definitions = [
            ("dashboard", "Vue d'ensemble", DashboardPage),
            ("catalog", "Catalogue", CatalogPage),
            ("suggestions", "À recommander", SuggestionsPage),
            ("new_order", "Nouvelle commande", OrderPage),
            ("orders", "Historique", OrdersPage),
            ("statistics", "Statistiques", StatisticsPage),
            ("suppliers", "Fournisseurs", SuppliersPage),
            ("import", "Mise à jour CAHPP", ImportPage),
            ("settings", "Paramètres", SettingsPage),
        ]
        for key, label, page_class in definitions:
            nav_row = tk.Frame(self.sidebar, bg=COLORS["nav"])
            nav_row.pack(fill="x")
            indicator = tk.Frame(
                nav_row,
                bg=COLORS["nav"],
                width=4,
            )
            indicator.pack(side="left", fill="y")
            indicator.pack_propagate(False)
            button = tk.Button(
                nav_row,
                text=label,
                anchor="w",
                bg=COLORS["nav"],
                activebackground=COLORS["nav_hover"],
                fg="white",
                activeforeground="white",
                bd=0,
                highlightthickness=0,
                font=("Segoe UI", 10),
                padx=16,
                pady=11,
                command=lambda selected=key: self.show_page(selected),
            )
            button.pack(side="left", fill="x", expand=True)
            self.nav_rows[key] = nav_row
            self.nav_indicators[key] = indicator
            self.nav_buttons[key] = button
            page = page_class(self.content, self)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = page

        self.version_label = tk.Label(
            self.sidebar,
            text=f"Version {__version__}",
            bg=COLORS["nav"],
            fg="#BDD6E5",
            font=("Segoe UI", 8),
            padx=20,
            pady=16,
            anchor="w",
        )
        self.version_label.pack(side="bottom", fill="x")
        self.sync_label = tk.Label(
            self.sidebar,
            text="",
            bg=COLORS["nav"],
            fg="#BDD6E5",
            font=("Segoe UI", 8),
            padx=20,
            pady=3,
            anchor="w",
            wraplength=170,
            justify="left",
        )
        self.sync_label.pack(side="bottom", fill="x")
        self.user_label = tk.Label(
            self.sidebar,
            text=self.database.current_user_name,
            bg=COLORS["nav"],
            fg="white",
            font=("Segoe UI Semibold", 9),
            padx=20,
            pady=3,
            anchor="w",
        )
        self.user_label.pack(side="bottom", fill="x")
        self.show_page("dashboard")
        self.root.after_idle(self._maximize_initial_window)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._ui_poll_id = self.root.after(40, self._drain_ui_events)
        self.root.after(1200, self._start_background_maintenance)
        self.root.after(1800, self._offer_shared_installer)
        if self.collaboration:
            self.root.after(700, self.sync_collaboration)
            self._start_periodic_collaboration()

    def _maximize_initial_window(self) -> None:
        """Utilise par défaut tout l'espace de travail disponible."""
        try:
            self.root.state("zoomed")
        except tk.TclError:
            try:
                self.root.attributes("-zoomed", True)
            except tk.TclError:
                pass

    def post_ui(self, callback) -> None:
        """Planifie une réponse de worker sans appeler Tcl depuis son thread."""
        if not self._closing:
            self._ui_events.put(callback)

    def _drain_ui_events(self) -> None:
        self._ui_poll_id = None
        if self._closing:
            return
        # Borne le travail à chaque passage pour laisser Tk traiter les événements.
        for _ in range(30):
            try:
                callback = self._ui_events.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except Exception as exc:
                log_failure(logger, "retour_worker_interface_echec", exc)
                self.root.report_callback_exception(type(exc), exc, exc.__traceback__)
            if self._closing:
                return
        self._ui_poll_id = self.root.after(40, self._drain_ui_events)

    def _refresh_locks_background(self) -> None:
        if self._heartbeat_running or not self.collaboration:
            return
        self._heartbeat_running = True
        manager = self.collaboration

        def worker():
            try:
                manager.refresh_active_locks()
            except Exception as exc:
                log_failure(logger, "heartbeat_echec", exc)
            finally:
                self.post_ui(lambda: setattr(self, "_heartbeat_running", False))

        threading.Thread(target=worker, daemon=True).start()

    def _configure_window_icon(self) -> None:
        icon_path = ROOT_DIR / "assets" / "app_icon.png"
        if not icon_path.is_file():
            return
        try:
            self._window_icon = tk.PhotoImage(file=str(icon_path))
            self.root.iconphoto(True, self._window_icon)
        except tk.TclError:
            self._window_icon = None

    def _initialize_user_and_collaboration(self) -> None:
        settings = self.database.get_settings()
        user_id = settings.get("user_id", "").strip()
        user_name = settings.get("user_name", "").strip()
        first_profile = not user_name
        if not user_id:
            user_id = str(uuid.uuid4())
        if not user_name:
            suggested = os.environ.get("USERNAME", "").strip()
            user_name = (
                simpledialog.askstring(
                    "Profil utilisateur",
                    ("Quel nom doit apparaître dans l'historique collaboratif ?"),
                    initialvalue=suggested,
                    parent=self.root,
                )
                or suggested
                or "Utilisateur"
            ).strip()
        self.database.save_settings({"user_id": user_id, "user_name": user_name})
        self.database.set_current_user(user_id, user_name)

        shared_path = settings.get("shared_workspace_path", "").strip()
        enabled = settings.get("collaboration_enabled", "0") == "1"
        if first_profile and not shared_path:
            configure = messagebox.askyesno(
                "Mode collaboratif",
                (
                    "Souhaitez-vous configurer maintenant le dossier partagé "
                    "utilisé avec votre collègue ?"
                ),
                parent=self.root,
            )
            if configure:
                selected = filedialog.askdirectory(
                    parent=self.root,
                    title="Choisir le dossier partagé",
                )
                if selected:
                    shared_path = selected
                    enabled = True
        if enabled and shared_path:
            manager = CollaborationManager(
                self.database, user_id, user_name, shared_path
            )
            try:
                manager.initialize_workspace()
            except (OSError, CollaborationError) as exc:
                configure_shared_workspace(None)
                messagebox.showwarning(
                    "Espace collaboratif indisponible",
                    (
                        f"{exc}\n\nL'application démarre en mode local. "
                        "Le chemin peut être corrigé dans Paramètres."
                    ),
                    parent=self.root,
                )
            else:
                self.collaboration = manager
                configure_shared_workspace(manager.root)
        else:
            configure_shared_workspace(None)

    def reconfigure_collaboration(self) -> None:
        if self.collaboration:
            self.collaboration.release_all_locks()
        settings = self.database.get_settings()
        user_id = settings.get("user_id", "").strip() or str(uuid.uuid4())
        user_name = settings.get("user_name", "").strip() or "Utilisateur"
        self.database.set_current_user(user_id, user_name)
        self.user_label.configure(text=user_name)
        enabled = settings.get("collaboration_enabled", "0") == "1"
        path = settings.get("shared_workspace_path", "").strip()
        if not enabled or not path:
            self.collaboration = None
            configure_shared_workspace(None)
            self.sync_label.configure(text="", fg="#BDD6E5")
            return
        manager = CollaborationManager(self.database, user_id, user_name, path)
        manager.initialize_workspace()
        self.collaboration = manager
        configure_shared_workspace(manager.root)
        self.sync_label.configure(text="Synchronisation…", fg="#BDD6E5")
        self._start_periodic_collaboration()
        self.sync_collaboration()

    def _start_periodic_collaboration(self) -> None:
        if self._periodic_started:
            return
        self._periodic_started = True
        self._schedule_periodic_collaboration()

    def _sync_interval_ms(self) -> int:
        raw = self.database.get_settings().get("sync_interval_seconds", "60")
        try:
            seconds = int(raw)
        except ValueError:
            seconds = 60
        return max(15, min(seconds, 3600)) * 1000

    def _schedule_periodic_collaboration(self) -> None:
        self._periodic_after_id = self.root.after(
            self._sync_interval_ms(), self._periodic_collaboration
        )

    def reschedule_periodic_collaboration(self) -> None:
        if self._periodic_after_id:
            self.root.after_cancel(self._periodic_after_id)
            self._periodic_after_id = None
        if self.collaboration:
            self._periodic_started = True
            self._schedule_periodic_collaboration()
        else:
            self._periodic_started = False

    def _has_unsaved_team_changes(self) -> bool:
        for name in ("settings", "suppliers"):
            page = self.pages.get(name)
            if page and page.has_unsaved_changes():
                return True
        return False

    def _periodic_collaboration(self) -> None:
        self._periodic_after_id = None
        if self.collaboration:
            self._refresh_locks_background()
            pause = (
                self.database.get_settings().get("pause_sync_while_editing", "1") != "0"
            )
            if pause and self._has_unsaved_team_changes():
                self.sync_label.configure(
                    text="Synchro en pause • saisie en cours",
                    fg="#F0C36A",
                )
            else:
                self.sync_collaboration()
            self._schedule_periodic_collaboration()
        else:
            self._periodic_started = False

    def sync_collaboration(self, show_errors: bool = False) -> None:
        if not self.collaboration or self._syncing:
            return
        self._syncing = True
        manager = self.collaboration
        self.sync_label.configure(text="Synchronisation…", fg="#BDD6E5")

        def worker() -> None:
            try:
                result = manager.sync_all()
            except Exception as exc:
                self.post_ui(
                    lambda error=exc: self._sync_finished(None, error, show_errors)
                )
            else:
                self.post_ui(
                    lambda value=result: self._sync_finished(value, None, show_errors)
                )

        threading.Thread(target=worker, daemon=True).start()

    def _sync_finished(
        self,
        result: dict[str, object] | None,
        error: Exception | None,
        show_errors: bool,
    ) -> None:
        self._syncing = False
        if error:
            log_failure(logger, "synchronisation_echec", error)
            self.last_sync_error = f"{type(error).__name__}: {error}"
            self.sync_label.configure(text="Hors ligne — cache local", fg="#F0C36A")
            if show_errors:
                messagebox.showwarning("Synchronisation", str(error), parent=self.root)
            if (
                self.active_page == "settings"
                and not self.pages["settings"].has_unsaved_changes()
            ):
                self.pages["settings"].refresh()
            return
        self.last_sync_result = result
        logger.info("synchronisation_terminee")
        self.last_sync_error = ""
        pending = len(self.database.pending_order_ids())
        if pending:
            self.sync_label.configure(
                text=f"{pending} commande(s) en attente",
                fg="#F0C36A",
            )
        else:
            self.sync_label.configure(
                text=f"Synchronisé • {datetime.now():%H:%M}",
                fg="#9FE0BE",
            )
        self.refresh_pages()
        if (
            self.active_page == "settings"
            and not self.pages["settings"].has_unsaved_changes()
        ):
            self.pages["settings"].refresh()
        if result and result.get("catalog_pending"):
            self._offer_shared_catalog()
        self._offer_shared_installer()

    def _offer_shared_catalog(self) -> None:
        if not self.collaboration:
            return
        manifest = self.collaboration.pending_catalog()
        if not manifest:
            return
        file_hash = str(manifest.get("sha256") or "")
        if file_hash == self._catalog_prompted_hash:
            return
        self._catalog_prompted_hash = file_hash
        if not messagebox.askyesno(
            "Nouveau catalogue partagé",
            (
                f"Le catalogue {manifest.get('version', '')} publié par "
                f"{manifest.get('published_by', 'un collègue')} est disponible.\n\n"
                "L'installer maintenant sur ce poste ?"
            ),
            parent=self.root,
        ):
            return
        page: ImportPage = self.pages["import"]  # type: ignore[assignment]
        self.show_page("import")
        page.start_shared_import(manifest)

    def _offer_shared_installer(self) -> None:
        if not self.collaboration:
            return
        settings = self.database.get_settings()
        try:
            installer = self.collaboration.pending_installer(
                __version__, settings.get("dismissed_installer_version", "")
            )
        except OSError:
            return
        if not installer:
            return
        version = str(installer.get("version") or "")
        if not version or version == self._installer_prompted_version:
            return
        self._installer_prompted_version = version
        choice = messagebox.askyesnocancel(
            "Mise à jour disponible",
            (
                f"La version {version} de Commandes CAHPP est disponible "
                "dans le dossier partagé.\n\n"
                "Oui : fermer l'application et lancer l'installation\n"
                "Non : ouvrir le dossier des mises à jour\n"
                "Annuler : me le rappeler plus tard"
            ),
            parent=self.root,
        )
        if choice is None:
            self._installer_prompted_version = ""
            return
        path = Path(str(installer.get("path") or ""))
        self.database.save_settings({"dismissed_installer_version": version})
        if choice:
            if not path.is_file():
                return
            try:
                if os.name == "nt":
                    os.startfile(str(path))  # type: ignore[attr-defined]
                else:
                    subprocess.Popen([str(path)])
            except OSError as exc:
                messagebox.showerror(
                    "Mise à jour",
                    f"L'installateur n'a pas pu être lancé :\n{exc}",
                    parent=self.root,
                )
                open_path(path.parent)
                return
            self.root.after(250, self.close)
        elif path.is_file():
            open_path(path.parent)

    def _start_background_maintenance(self) -> None:
        settings = self.database.get_settings()
        try:
            integrity_days = int(settings.get("integrity_check_days", "7"))
        except ValueError:
            integrity_days = 7
        integrity_due = timestamp_is_due(
            settings.get("last_integrity_check_at", ""), integrity_days
        )
        automatic_archive = settings.get("automatic_archive_enabled", "0") == "1"
        maintenance_due = timestamp_is_due(settings.get("last_maintenance_at", ""), 7)
        if not integrity_due and not maintenance_due:
            return

        def worker() -> None:
            integrity: tuple[bool, str] | None = None
            archived_ids: list[int] = []
            if integrity_due:
                integrity = self.database.quick_integrity_check()
                self.database.save_settings(
                    {
                        "last_integrity_check_at": datetime.now().isoformat(
                            timespec="seconds"
                        ),
                        "last_integrity_check_result": (
                            "OK" if integrity[0] else integrity[1]
                        ),
                    }
                )
            if maintenance_due:
                self.database.optimize_database()
                try:
                    months = int(settings.get("archive_after_months", "24"))
                except ValueError:
                    months = 24
                if automatic_archive:
                    archived_ids = self.database.archive_old_orders(
                        months_before(date.today(), max(1, months))
                    )
                self.database.save_settings(
                    {
                        "last_maintenance_at": datetime.now().isoformat(
                            timespec="seconds"
                        )
                    }
                )
            self.post_ui(
                lambda: self._background_maintenance_finished(integrity, archived_ids),
            )

        threading.Thread(target=worker, daemon=True).start()

    def _background_maintenance_finished(
        self,
        integrity: tuple[bool, str] | None,
        archived_ids: list[int],
    ) -> None:
        self.refresh_pages()
        if integrity is not None and not integrity[0]:
            messagebox.showerror(
                "Intégrité de la base",
                "Le contrôle de la base a détecté une anomalie :\n\n" + integrity[1],
                parent=self.root,
            )
        if archived_ids and self.collaboration:
            self.sync_collaboration()

    def sync_team_data(self) -> None:
        self.sync_collaboration(show_errors=True)

    def publish_order(self, order_id: int) -> bool:
        if not self.collaboration:
            return True
        try:
            self.collaboration.publish_order(order_id)
            self.sync_label.configure(
                text=f"Synchronisé • {datetime.now():%H:%M}",
                fg="#9FE0BE",
            )
            return True
        except (OSError, CollaborationError) as exc:
            self.sync_label.configure(text="À synchroniser", fg="#F0C36A")
            messagebox.showwarning(
                "Commande non synchronisée",
                (
                    f"La commande reste enregistrée localement.\n\n{exc}\n\n"
                    "Utilisez « Synchroniser maintenant » lorsque le partage "
                    "sera disponible."
                ),
                parent=self.root,
            )
            return False

    def reserve_order_number(self, selected_date: date | None = None) -> str | None:
        if not self.collaboration:
            return None
        return self.collaboration.reserve_order_number(selected_date)

    def acquire_order_lock(self, order_id: int) -> ResourceLock | None:
        if not self.collaboration:
            return None
        order, _ = self.database.get_order(order_id)
        try:
            return self.collaboration.acquire_lock("commande", str(order["shared_uid"]))
        except ResourceLockedError as exc:
            messagebox.showinfo(
                "Commande en cours d'utilisation",
                (
                    f"Cette commande est actuellement ouverte par "
                    f"{exc.owner or 'votre collègue'}.\n\n"
                    "Elle reste consultable mais ne peut pas être modifiée."
                ),
                parent=self.root,
            )
            return None
        except (OSError, CollaborationError) as exc:
            self.sync_label.configure(text="Hors connexion", fg="#F0C36A")
            messagebox.showwarning(
                "Partage indisponible",
                (
                    "Le verrou collaboratif ne peut pas être obtenu. La commande "
                    "reste consultable, mais sa modification est bloquée pour "
                    f"éviter un conflit.\n\n{exc}"
                ),
                parent=self.root,
            )
            return None

    @contextmanager
    def locked_order(self, order_id: int):
        handle = self.acquire_order_lock(order_id)
        if self.collaboration and handle is None:
            yield False
            return
        try:
            yield True
        finally:
            if handle:
                handle.release()

    @contextmanager
    def locked_product(self, product_id: int):
        if not self.collaboration:
            yield True
            return
        product = self.database.get_product(product_id)
        if product is None:
            yield False
            return
        try:
            handle = self.collaboration.acquire_lock(
                "produit", str(product["code_cahpp"])
            )
        except ResourceLockedError as exc:
            messagebox.showinfo(
                "Article en cours de modification",
                (
                    f"Cet article est actuellement modifié par "
                    f"{exc.owner or 'votre collègue'}."
                ),
                parent=self.root,
            )
            yield False
            return
        except (OSError, CollaborationError) as exc:
            self.sync_label.configure(text="Hors connexion", fg="#F0C36A")
            messagebox.showwarning(
                "Partage indisponible",
                (
                    "Le verrou collaboratif ne peut pas être obtenu. La fiche "
                    "reste consultable, mais sa modification est bloquée pour "
                    f"éviter un conflit.\n\n{exc}"
                ),
                parent=self.root,
            )
            yield False
            return
        try:
            yield True
        finally:
            handle.release()

    def close(self, force: bool = False) -> None:
        if self._closing:
            return
        if not force and any(p.has_unsaved_changes() for p in self.pages.values()):
            if not messagebox.askyesno(
                "Saisies non enregistrées",
                "Certaines modifications ne sont pas enregistrées.\n\n"
                "Quitter et les abandonner ? Pour les conserver, annulez puis "
                "utilisez Enregistrer dans l'écran concerné.",
                icon="warning",
                parent=self.root,
            ):
                return
        self._closing = True
        if self._ui_poll_id:
            self.root.after_cancel(self._ui_poll_id)
        if self._periodic_after_id:
            self.root.after_cancel(self._periodic_after_id)
        for page in self.pages.values():
            page.shutdown()
        if self.collaboration:
            self.collaboration.release_all_locks()
        self.root.destroy()

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure(
            "TFrame",
            background=COLORS["background"],
        )
        style.configure(
            "Surface.TFrame",
            background=COLORS["surface"],
        )
        style.configure(
            "TLabel",
            background=COLORS["background"],
            foreground=COLORS["text"],
            font=("Segoe UI", 9),
        )
        style.configure(
            "Surface.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["text"],
        )
        style.configure(
            "Success.Surface.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["success"],
            font=("Segoe UI Semibold", 9),
        )
        style.configure(
            "Title.TLabel",
            font=("Segoe UI Semibold", 20),
            foreground=COLORS["text"],
        )
        style.configure(
            "Subtitle.TLabel",
            font=("Segoe UI", 10),
            foreground=COLORS["muted"],
        )
        style.configure(
            "Accent.TButton",
            font=("Segoe UI Semibold", 9),
            padding=(12, 7),
        )
        style.configure("TButton", font=("Segoe UI", 9), padding=(9, 6))
        style.configure(
            "Treeview",
            font=("Segoe UI", 9),
            rowheight=28,
            background="white",
            fieldbackground="white",
            bordercolor=COLORS["border"],
        )
        style.configure(
            "Treeview.Heading",
            font=("Segoe UI Semibold", 9),
            padding=(6, 7),
        )
        style.configure("TEntry", padding=5)
        style.configure("TCombobox", padding=4)

    def show_page(self, name: str) -> None:
        for key, button in self.nav_buttons.items():
            selected = key == name
            background = COLORS["nav_active"] if selected else COLORS["nav"]
            self.nav_rows[key].configure(bg=background)
            self.nav_indicators[key].configure(
                bg=COLORS["nav_indicator"] if selected else COLORS["nav"]
            )
            button.configure(
                bg=background,
                font=(("Segoe UI Semibold", 10) if selected else ("Segoe UI", 10)),
            )
        self.active_page = name
        page = self.pages[name]
        page.tkraise()
        page.refresh()
        page.after_idle(page.fit_visible_columns)

    def refresh_pages(self) -> None:
        for page in self.pages.values():
            page.invalidate()
