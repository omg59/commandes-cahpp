from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import threading
import tkinter as tk
import uuid
import webbrowser
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable

from . import __version__
from .catalog_importer import CatalogImporter, ImportResult
from .collaboration import (
    CollaborationError,
    CollaborationManager,
    ResourceLock,
    ResourceLockedError,
    SyncConflictError,
)
from .database import Database
from .local_services import (
    MAIL_TEMPLATE_VARIABLES,
    attach_document,
    create_complete_backup,
    configure_shared_workspace,
    mark_order_sent,
    portable_path,
    prepare_mail_order,
    remove_document,
    resolve_portable_path,
)
from .paths import BACKUP_DIR, EXPORT_DIR
from .pdf_export import generate_order_pdf


COLORS = {
    "nav": "#123A5A",
    "nav_hover": "#1A5276",
    "nav_active": "#0B2B43",
    "nav_indicator": "#65C7E8",
    "accent": "#1F6F9F",
    "accent_light": "#E8F2F8",
    "background": "#F3F6F8",
    "surface": "#FFFFFF",
    "text": "#1E2933",
    "muted": "#64748B",
    "border": "#D8E1E8",
    "success": "#277A53",
    "warning": "#A36400",
    "danger": "#A33A3A",
}


class FeedbackButton(tk.Button):
    """Bouton d'action avec confirmation visuelle temporaire non bloquante."""

    def __init__(
        self,
        parent,
        *,
        text: str,
        command: Callable[[], bool],
        success_text: str = "✓ Enregistré",
    ):
        self._action = command
        self._default_text = text
        self._success_text = success_text
        self._restore_after_id: str | None = None
        super().__init__(
            parent,
            text=text,
            command=self._run_action,
            bg=COLORS["accent"],
            activebackground=COLORS["nav_hover"],
            fg="white",
            activeforeground="white",
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Segoe UI Semibold", 9),
            padx=12,
            pady=7,
            cursor="hand2",
        )

    def _run_action(self) -> None:
        if self._action():
            self.show_success()

    def show_success(self) -> None:
        if self._restore_after_id:
            self.after_cancel(self._restore_after_id)
        self.configure(
            text=self._success_text,
            bg=COLORS["success"],
            activebackground=COLORS["success"],
        )
        self._restore_after_id = self.after(2000, self._restore)

    def _restore(self) -> None:
        self.configure(
            text=self._default_text,
            bg=COLORS["accent"],
            activebackground=COLORS["nav_hover"],
        )
        self._restore_after_id = None


def format_number(value: object, decimals: int = 0) -> str:
    if value in (None, ""):
        return "—"
    number = Decimal(str(value))
    if decimals == 0 and number == number.to_integral():
        return f"{int(number):,}".replace(",", " ")
    text = f"{number:.{decimals}f}".replace(".", ",")
    return text


def format_price(value: object, decimals: int = 4) -> str:
    if value is None:
        return "Prix absent"
    return f"{Decimal(str(value)):.{decimals}f}".replace(".", ",") + " €"


def format_timestamp(value: object) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(str(value)).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return str(value)


def format_pack(row) -> str:
    quantity = format_number(row["conditionnement"])
    detail = str(row["unit_packaging"] or "").strip()
    return f"{quantity} • {detail}" if detail else quantity


def open_path(path: Path | str) -> None:
    path = str(path)
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", path])


def safe_filename(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*]+', "-", value)
    value = re.sub(r"\s+", " ", value).strip(" .-")
    return value or "fournisseur"


def filter_supplier_names(names: list[str], query: str) -> list[str]:
    query = query.strip().casefold()
    if not query:
        return names
    return [name for name in names if query in name.casefold()]


def configured_pdf_directory(database: Database) -> Path:
    configured = database.get_settings().get("pdf_default_directory", "").strip()
    if configured:
        directory = resolve_portable_path(os.path.expandvars(configured))
        if directory.is_dir():
            return directory
    return EXPORT_DIR


def suggested_pdf_filename(database: Database, order) -> str:
    sequence = database.daily_supplier_order_sequence(int(order["id"]))
    suffix = "" if sequence == 1 else f"_{sequence}"
    supplier = safe_filename(str(order["supplier_name"]).title())
    return f"BC-{order['order_date']}{suffix}_{supplier}.pdf"


def fractional_carton_lines(lines: list[dict[str, object]]) -> list[str]:
    issues = []
    for line in lines:
        cartons = Decimal(str(line.get("cartons") or 0))
        if cartons != cartons.to_integral_value():
            issues.append(str(line.get("designation") or "Article"))
    return issues


def choose_pdf_path(parent, database: Database, order) -> Path | None:
    default_name = suggested_pdf_filename(database, order)
    selected = filedialog.asksaveasfilename(
        parent=parent,
        title="Enregistrer le bon de commande",
        initialdir=str(configured_pdf_directory(database)),
        initialfile=default_name,
        defaultextension=".pdf",
        filetypes=[("Document PDF", "*.pdf"), ("Tous les fichiers", "*.*")],
    )
    return Path(selected) if selected else None


class App(ttk.Frame):
    def __init__(self, root: tk.Tk, database: Database):
        super().__init__(root)
        self.root = root
        self.database = database
        self._syncing = False
        self._catalog_prompted_hash = ""
        self._periodic_started = False
        self.collaboration: CollaborationManager | None = None
        self._initialize_user_and_collaboration()
        self.root.title("Commandes CAHPP")
        self.root.geometry("1320x820")
        self.root.minsize(1060, 680)
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
            ("new_order", "Nouvelle commande", OrderPage),
            ("orders", "Historique", OrdersPage),
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
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        if self.collaboration:
            self.root.after(700, self.sync_collaboration)
            self._start_periodic_collaboration()

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
                    (
                        "Quel nom doit apparaître dans l'historique "
                        "collaboratif ?"
                    ),
                    initialvalue=suggested,
                    parent=self.root,
                )
                or suggested
                or "Utilisateur"
            ).strip()
        self.database.save_settings(
            {"user_id": user_id, "user_name": user_name}
        )
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
        manager = CollaborationManager(
            self.database, user_id, user_name, path
        )
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
        self.root.after(30000, self._periodic_collaboration)

    def _periodic_collaboration(self) -> None:
        if self.collaboration:
            self.collaboration.refresh_active_locks()
            self.sync_collaboration()
            self.root.after(30000, self._periodic_collaboration)
        else:
            self._periodic_started = False

    def sync_collaboration(self, show_errors: bool = False) -> None:
        if not self.collaboration or self._syncing:
            return
        self._syncing = True
        self.sync_label.configure(text="Synchronisation…", fg="#BDD6E5")

        def worker() -> None:
            try:
                result = self.collaboration.sync_all()
            except Exception as exc:
                self.root.after(
                    0, lambda error=exc: self._sync_finished(None, error, show_errors)
                )
            else:
                self.root.after(
                    0, lambda value=result: self._sync_finished(value, None, show_errors)
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
            self.sync_label.configure(
                text="Hors ligne — cache local", fg="#F0C36A"
            )
            if show_errors:
                messagebox.showwarning(
                    "Synchronisation", str(error), parent=self.root
                )
            return
        self.sync_label.configure(
            text=f"Synchronisé • {datetime.now():%H:%M}",
            fg="#9FE0BE",
        )
        self.refresh_pages()
        if result and result.get("catalog_pending"):
            self._offer_shared_catalog()

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
            self.sync_label.configure(
                text="À synchroniser", fg="#F0C36A"
            )
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
            return self.collaboration.acquire_lock(
                "commande", str(order["shared_uid"])
            )
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

    def close(self) -> None:
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
            background = (
                COLORS["nav_active"] if selected else COLORS["nav"]
            )
            self.nav_rows[key].configure(bg=background)
            self.nav_indicators[key].configure(
                bg=COLORS["nav_indicator"] if selected else COLORS["nav"]
            )
            button.configure(
                bg=background,
                font=(
                    ("Segoe UI Semibold", 10)
                    if selected
                    else ("Segoe UI", 10)
                ),
            )
        self.active_page = name
        page = self.pages[name]
        page.tkraise()
        page.refresh()

    def refresh_pages(self) -> None:
        for page in self.pages.values():
            page.invalidate()


class BasePage(ttk.Frame):
    def __init__(self, parent, app: App):
        super().__init__(parent, padding=22)
        self.app = app
        self.database = app.database
        self._valid = False

    def header(self, title: str, subtitle: str) -> None:
        ttk.Label(self, text=title, style="Title.TLabel").pack(anchor="w")
        ttk.Label(self, text=subtitle, style="Subtitle.TLabel").pack(
            anchor="w", pady=(2, 18)
        )

    def invalidate(self) -> None:
        self._valid = False

    def refresh(self) -> None:
        self._valid = True


class DashboardPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header(
            "Vue d'ensemble",
            "Catalogue, fournisseurs et commandes disponibles sur ce poste.",
        )
        self.cards = ttk.Frame(self)
        self.cards.pack(fill="x")
        self.card_values: dict[str, tk.Label] = {}
        for index, (key, label) in enumerate(
            [
                ("products", "Articles actifs"),
                ("suppliers", "Fournisseurs"),
                ("favorites", "Articles favoris"),
                ("orders", "Commandes"),
            ]
        ):
            card = tk.Frame(
                self.cards,
                bg=COLORS["surface"],
                highlightbackground=COLORS["border"],
                highlightthickness=1,
                padx=16,
                pady=14,
            )
            card.grid(row=0, column=index, sticky="ew", padx=(0, 12))
            self.cards.columnconfigure(index, weight=1)
            value = tk.Label(
                card,
                text="0",
                bg=COLORS["surface"],
                fg=COLORS["accent"],
                font=("Segoe UI Semibold", 22),
                anchor="w",
            )
            value.pack(fill="x")
            tk.Label(
                card,
                text=label,
                bg=COLORS["surface"],
                fg=COLORS["muted"],
                font=("Segoe UI", 9),
                anchor="w",
            ).pack(fill="x")
            self.card_values[key] = value

        self.import_box = tk.Frame(
            self,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        self.import_box.pack(fill="x", pady=(20, 0))
        self.import_label = tk.Label(
            self.import_box,
            text="Aucun catalogue importé",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=("Segoe UI Semibold", 11),
            anchor="w",
        )
        self.import_label.pack(fill="x")
        self.import_detail = tk.Label(
            self.import_box,
            text="",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
            anchor="w",
        )
        self.import_detail.pack(fill="x", pady=(4, 0))

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(20, 0))
        ttk.Button(
            actions,
            text="Préparer une commande",
            style="Accent.TButton",
            command=lambda: self.app.show_page("new_order"),
        ).pack(side="left")
        ttk.Button(
            actions,
            text="Importer un catalogue",
            command=lambda: self.app.show_page("import"),
        ).pack(side="left", padx=8)

    def refresh(self) -> None:
        stats = self.database.dashboard_stats()
        for key, label in self.card_values.items():
            label.configure(text=f"{int(stats[key]):,}".replace(",", " "))
        latest = stats["latest_import"]
        if latest:
            when = datetime.fromisoformat(latest["imported_at"]).strftime(
                "%d/%m/%Y à %H:%M"
            )
            self.import_label.configure(text=latest["filename"])
            self.import_detail.configure(
                text=f"Dernier import le {when} • "
                f"{int(latest['row_count']):,} articles".replace(",", " ")
            )
        else:
            self.import_label.configure(text="Aucun catalogue importé")
            self.import_detail.configure(
                text="Commencez par importer la base tarifaire CAHPP."
            )
        self._valid = True


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
        self.supplier_box.bind("<<ComboboxSelected>>", lambda event: self.search())
        self.favorite_var = tk.BooleanVar()
        ttk.Checkbutton(
            filters,
            text="Favoris uniquement",
            variable=self.favorite_var,
            command=self.search,
        ).pack(side="left", padx=10)
        ttk.Button(filters, text="Rechercher", command=self.search).pack(
            side="right"
        )

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

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", pady=(10, 0))
        self.result_label = ttk.Label(
            bottom, text="", style="Subtitle.TLabel"
        )
        self.result_label.pack(side="left")
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
        self._after_id = None

    def _schedule_search(self, event=None) -> None:
        if self._after_id:
            self.after_cancel(self._after_id)
        self._after_id = self.after(300, self.search)

    def _load_suppliers(self) -> None:
        suppliers = self.database.list_suppliers(used_only=True)
        self.supplier_map = {"Tous les fournisseurs": None}
        self.supplier_map.update({row["name"]: row["id"] for row in suppliers})
        values = list(self.supplier_map)
        current = self.supplier_var.get()
        self.supplier_box["values"] = values
        if current not in self.supplier_map:
            self.supplier_var.set(values[0] if values else "")

    def search(self) -> None:
        supplier_id = self.supplier_map.get(self.supplier_var.get())
        rows = self.database.search_products(
            query=self.search_var.get(),
            supplier_id=supplier_id,
            favorite_only=self.favorite_var.get(),
            limit=300,
        )
        self.tree.delete(*self.tree.get_children())
        for row in rows:
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
        suffix = " (limite 300)" if len(rows) == 300 else ""
        self.result_label.configure(
            text=f"{len(rows)} résultat(s){suffix}"
        )
        self.update_product_actions()

    def selected_product_id(self) -> int | None:
        selected = self.tree.selection()
        return int(selected[0]) if selected else None

    def update_product_actions(self) -> None:
        product_id = self.selected_product_id()
        product = self.database.get_product(product_id) if product_id else None
        self.delete_product_button.configure(
            state=(
                "normal"
                if product and product["source"] == "LOCAL"
                else "disabled"
            )
        )
        self.reset_product_button.configure(
            state=(
                "normal"
                if product and product["has_override"]
                else "disabled"
            )
        )
        self.edit_product_button.configure(
            state="normal" if product else "disabled"
        )

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
            self.database.set_favorite(
                product_id, not bool(product["favorite"])
            )
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
        self.search()
        self._valid = True


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
        self.geometry("650x500")
        self.minsize(580, 450)
        self.transient(parent.winfo_toplevel())
        self.grab_set()

        surface = ttk.Frame(self, padding=20)
        surface.pack(fill="both", expand=True)
        ttk.Label(
            surface,
            text=str(self.product["designation"]),
            font=("Segoe UI Semibold", 14),
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
        ]
        self.vars: dict[str, tk.StringVar] = {}
        for row, (label, key) in enumerate(definitions, start=2):
            ttk.Label(surface, text=label).grid(
                row=row, column=0, sticky="w", pady=7
            )
            value = self.product[key]
            variable = tk.StringVar(
                value="" if value is None else str(value).replace(".", ",")
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
                row=8, column=0, columnspan=2, sticky="w", pady=(12, 0)
            )

        actions = ttk.Frame(surface)
        actions.grid(row=9, column=0, columnspan=2, sticky="e", pady=(20, 0))
        ttk.Button(actions, text="Annuler", command=self.destroy).pack(
            side="left"
        )
        ttk.Button(
            actions,
            text="Enregistrer",
            style="Accent.TButton",
            command=self.save,
        ).pack(side="left", padx=(8, 0))
        surface.columnconfigure(1, weight=1)

    def save(self) -> None:
        try:
            designation = self.vars["designation"].get().strip()
            if not designation:
                raise ValueError("La désignation est obligatoire.")
            conditionnement = float(
                self.vars["conditionnement"].get().replace(",", ".")
            )
            unit_price = float(
                self.vars["unit_price"].get().replace(",", ".")
            )
            vat = float(self.vars["vat"].get().replace(",", "."))
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
                self.database.set_product_override(self.product_id, **values)
            self.saved = True
            self.destroy()
        except ValueError as exc:
            messagebox.showerror("Article", str(exc), parent=self)


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

        ttk.Label(
            left, text="Articles disponibles", style="Surface.TLabel"
        ).pack(anchor="w")
        search_row = ttk.Frame(left, style="Surface.TFrame")
        search_row.pack(fill="x", pady=(8, 8))
        self.product_search_var = tk.StringVar()
        search_entry = ttk.Entry(
            search_row, textvariable=self.product_search_var
        )
        search_entry.pack(side="left", fill="x", expand=True)
        search_entry.bind("<KeyRelease>", self._schedule_search)
        ttk.Button(
            search_row, text="Chercher", command=self.search_products
        ).pack(side="left", padx=(6, 0))

        self.product_tree = ttk.Treeview(
            left,
            columns=("ref", "designation", "pack", "price"),
            show="headings",
            selectmode="browse",
            height=14,
        )
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
        self.product_tree.pack(fill="both", expand=True)
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

        ttk.Label(
            right, text="Contenu de la commande", style="Surface.TLabel"
        ).pack(anchor="w")
        self.cart_tree = ttk.Treeview(
            right,
            columns=("designation", "ref", "cartons", "pack", "price", "total"),
            show="headings",
            selectmode="browse",
            height=15,
        )
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
        self.cart_tree.pack(fill="both", expand=True, pady=(8, 0))
        self.cart_tree.bind("<Double-1>", lambda event: self.edit_quantity())

        cart_buttons = ttk.Frame(right, style="Surface.TFrame")
        cart_buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(
            cart_buttons, text="Modifier la quantité", command=self.edit_quantity
        ).pack(side="left")
        ttk.Button(
            cart_buttons, text="Retirer", command=self.remove_line
        ).pack(side="left", padx=6)
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
            text="Générer le PDF",
            command=self.save_and_generate,
            success_text="✓ PDF généré",
        )
        self.generate_button.pack(side="right", padx=(0, 8))

        self.supplier_map: dict[str, int] = {}
        self._all_supplier_names: list[str] = []
        self.cart: list[dict[str, object]] = []
        self._search_after = None
        self._previous_supplier = ""
        self.current_order_id: int | None = None
        self.current_order_date: date | None = None
        self.current_order_lock: ResourceLock | None = None

    def _schedule_search(self, event=None) -> None:
        if self._search_after:
            self.after_cancel(self._search_after)
        self._search_after = self.after(250, self.search_products)

    def load_suppliers(self) -> None:
        suppliers = self.database.list_suppliers(used_only=True)
        self.supplier_map = {row["name"]: row["id"] for row in suppliers}
        self._all_supplier_names = list(self.supplier_map)
        self.supplier_box["values"] = self._all_supplier_names
        if self.supplier_var.get() not in self.supplier_map:
            self.supplier_var.set("")

    def _filter_suppliers(self, event=None) -> None:
        if event and event.keysym in {
            "Up",
            "Down",
            "Left",
            "Right",
            "Escape",
            "Tab",
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
            return

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
                messages.append(
                    f"Minimum : manque {format_price(difference, 2)}"
                )
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

    def search_products(self) -> None:
        supplier_id = self.selected_supplier_id()
        self.product_tree.delete(*self.product_tree.get_children())
        if not supplier_id:
            return
        rows = self.database.search_products(
            query=self.product_search_var.get(),
            supplier_id=supplier_id,
            favorite_only=not bool(self.product_search_var.get().strip()),
            limit=200,
        )
        if not rows and not self.product_search_var.get().strip():
            rows = self.database.search_products(
                supplier_id=supplier_id, favorite_only=False, limit=100
            )
        for row in rows:
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

    def add_product(self) -> None:
        selected = self.product_tree.selection()
        if not selected:
            return
        self.add_product_by_id(int(selected[0]))

    def add_product_by_id(self, product_id: int) -> None:
        product = self.database.get_product(product_id)
        if product is None:
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
            (
                item
                for item in self.cart
                if item["product_id"] == int(product["id"])
            ),
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
                    "designation": product["short_name"]
                    or product["designation"],
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
            self.product_tree.selection_set(str(dialog.product_id))
            self.add_product()

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

    def load_order(
        self, order_id: int, lock: ResourceLock | None = None
    ) -> None:
        order, lines = self.database.get_order(order_id)
        if order["status"] != "Brouillon":
            raise ValueError("Seuls les brouillons peuvent être modifiés.")
        self.current_order_id = order_id
        self.current_order_lock = lock
        self.current_order_date = date.fromisoformat(order["order_date"])
        self.supplier_var.set(order["supplier_name"])
        self._previous_supplier = order["supplier_name"]
        self.notes_var.set(order["notes"] or "")
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
        self.mode_label.configure(
            text=f"Modification de {order['order_number']}"
        )
        self.search_products()
        self.refresh_cart()

    def reset_order(self, confirm: bool = True) -> bool:
        if confirm and (self.cart or self.current_order_id):
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
        self.supplier_var.set("")
        self._previous_supplier = ""
        self.mode_label.configure(text="")
        self.franco_label.configure(text="")
        self.product_tree.delete(*self.product_tree.get_children())
        self.refresh_cart()
        return True

    def _confirm_order_warnings(self, supplier_id: int) -> bool:
        warnings = []
        fractional = fractional_carton_lines(self.cart)
        if fractional:
            sample = "\n".join(f"• {name}" for name in fractional[:5])
            more = "\n…" if len(fractional) > 5 else ""
            warnings.append(
                "Le nombre de cartons n'est pas entier pour :\n"
                f"{sample}{more}"
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
            )
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
        self.mode_label.configure(
            text=f"Modification de {order['order_number']}"
        )
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
            generate_order_pdf(self.database, order_id, output)
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
        self.load_suppliers()
        self.search_products()
        self._valid = True


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
            ttk.Label(frame, text=label).grid(
                row=row, column=0, sticky="w", pady=5
            )
            ttk.Entry(frame, textvariable=self.vars[key], width=42).grid(
                row=row, column=1, sticky="ew", padx=(10, 0), pady=5
            )
        buttons = ttk.Frame(frame)
        buttons.grid(row=len(fields), column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Annuler", command=self.destroy).pack(
            side="left"
        )
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
            pack = float(self.vars["pack"].get().replace(",", "."))
            price = float(self.vars["price"].get().replace(",", "."))
            vat = float(self.vars["vat"].get().replace(",", "."))
            if pack <= 0:
                raise ValueError(
                    "Le conditionnement doit être supérieur à zéro."
                )
            if price < 0 or vat < 0:
                raise ValueError(
                    "Le prix et la TVA ne peuvent pas être négatifs."
                )
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
            text="Ajouter un bon de livraison",
            style="Accent.TButton",
            command=lambda: self.add_files("Bon de livraison", False),
        ).pack(side="left")
        ttk.Button(
            actions,
            text="Ajouter une pièce au mail",
            command=lambda: self.add_files("Pièce jointe e-mail", True),
        ).pack(side="left", padx=6)
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
            text="Inclure / exclure du mail",
            command=self.toggle_email,
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
        y = parent_window.winfo_rooty() + (
            parent_window.winfo_height() - height
        ) // 2
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
                ("Documents", "*.pdf;*.png;*.jpg;*.jpeg;*.doc;*.docx;*.xlsx"),
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
                "Certains fichiers n'ont pas pu être ajoutés :\n"
                + "\n".join(errors),
                parent=self,
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


class OrdersPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header(
            "Historique des commandes",
            "Recherchez, dupliquez et rattachez les documents de livraison.",
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
            values=("Tous", "Brouillon", "Générée", "E-mail préparé", "Envoyée"),
        )
        status_box.pack(side="left", padx=7)
        status_box.bind("<<ComboboxSelected>>", lambda event: self.refresh())
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
                "sync",
                "ht",
                "ttc",
            ),
            show="headings",
        )
        for column, title, width in (
            ("number", "N° commande", 125),
            ("created", "Créée le", 128),
            ("author", "Créée par", 90),
            ("sent", "Envoyée le", 128),
            ("supplier", "Fournisseur", 180),
            ("status", "Statut", 95),
            ("sync", "Synchro", 95),
            ("ht", "Total HT", 90),
            ("ttc", "Total TTC", 90),
        ):
            self.tree.heading(column, text=title)
            self.tree.column(
                column,
                width=width,
                stretch=column == "supplier",
                anchor="w" if column == "supplier" else "center",
        )
        scrollbar = ttk.Scrollbar(
            frame, orient="vertical", command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda event: self.edit_draft())
        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(
            actions,
            text="Modifier le brouillon",
            style="Accent.TButton",
            command=self.edit_draft,
        ).pack(side="left")
        ttk.Button(
            actions,
            text="Dupliquer",
            command=self.duplicate,
        ).pack(side="left", padx=6)
        ttk.Button(
            actions,
            text="Documents / bon de livraison",
            command=self.manage_documents,
        ).pack(side="left")
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
        ttk.Button(
            actions, text="Marquer envoyée", command=self.mark_sent
        ).pack(side="right", padx=6)
        ttk.Button(
            actions, text="Ouvrir le PDF", command=self.open_pdf
        ).pack(side="right")
        self.regenerate_button = FeedbackButton(
            actions,
            text="Regénérer le PDF",
            command=self.regenerate_pdf,
            success_text="✓ PDF régénéré",
        )
        self.regenerate_button.pack(side="right", padx=6)
        self._refresh_after = None

    def _schedule_refresh(self, event=None) -> None:
        if self._refresh_after:
            self.after_cancel(self._refresh_after)
        self._refresh_after = self.after(250, self.refresh)

    def selected_order(self):
        selected = self.tree.selection()
        return int(selected[0]) if selected else None

    def edit_draft(self) -> None:
        order_id = self.selected_order()
        if not order_id:
            return
        order, _ = self.database.get_order(order_id)
        if order["status"] != "Brouillon":
            messagebox.showinfo(
                "Modification",
                "Cette commande a déjà été générée. Seuls les brouillons "
                "peuvent être modifiés.",
                parent=self,
            )
            return
        lock = self.app.acquire_order_lock(order_id)
        if self.app.collaboration and lock is None:
            return
        self.app.show_page("new_order")
        order_page: OrderPage = self.app.pages["new_order"]  # type: ignore[assignment]
        order_page.load_order(order_id, lock=lock)

    def duplicate(self) -> None:
        order_id = self.selected_order()
        if not order_id:
            messagebox.showinfo(
                "Dupliquer", "Sélectionnez une commande.", parent=self
            )
            return
        try:
            reserved = self.app.reserve_order_number(date.today())
            new_id = self.database.duplicate_order(
                order_id, order_number=reserved
            )
        except (OSError, CollaborationError) as exc:
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
            messagebox.showinfo(
                "Documents", "Sélectionnez une commande.", parent=self
            )
            return
        with self.app.locked_order(order_id) as allowed:
            if not allowed:
                return
            dialog = OrderDocumentsDialog(self, self.database, order_id)
            self.wait_window(dialog)
            self.app.publish_order(order_id)
        self.refresh()

    def show_audit(self) -> None:
        order_id = self.selected_order()
        if not order_id:
            messagebox.showinfo(
                "Journal", "Sélectionnez une commande.", parent=self
            )
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
        scrollbar = ttk.Scrollbar(
            frame, orient="vertical", command=tree.yview
        )
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
            resolve_portable_path(order["pdf_path"])
            if order["pdf_path"]
            else None
        )
        if pdf_path and pdf_path.is_file():
            open_path(pdf_path)
        else:
            messagebox.showinfo(
                "PDF", "Aucun PDF n'a encore été généré.", parent=self
            )

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
            generate_order_pdf(self.database, order_id, output)
            self.app.publish_order(order_id)
            self.refresh()
            open_path(output.parent)
            return True

    def prepare_email(self) -> None:
        order_id = self.selected_order()
        if not order_id:
            messagebox.showinfo(
                "E-mail", "Sélectionnez une commande.", parent=self
            )
            return
        with self.app.locked_order(order_id) as allowed:
            if not allowed:
                return
            try:
                compose_url, folder, _ = prepare_mail_order(
                    self.database, order_id
                )
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

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        status = self.status_var.get()
        orders = self.database.list_orders(
            query=self.search_var.get(),
            status="" if status == "Tous" else status,
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
                    order["sync_state"],
                    format_price(order["total_ht"], 2),
                    format_price(order["total_ttc"], 2),
                ),
            )
        self.result_label.configure(text=f"{len(orders)} commande(s)")
        self._valid = True


class SuppliersPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
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
        self.notes.grid(
            row=notes_row, column=1, sticky="nsew", padx=(12, 0), pady=6
        )
        right.columnconfigure(1, weight=1)
        right.rowconfigure(notes_row, weight=1)
        self.save_button = FeedbackButton(
            right,
            text="Enregistrer",
            command=self.save,
            success_text="✓ Fournisseur enregistré",
        )
        self.save_button.grid(
            row=notes_row + 1, column=1, sticky="e", pady=(12, 0)
        )
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
        selected = self.tree.selection()
        if not selected:
            return
        supplier = self.database.get_supplier(int(selected[0]))
        for key, variable in self.fields.items():
            value = supplier[key]
            variable.set("" if value is None else str(value).replace(".", ","))
        self.notes.delete("1.0", "end")
        self.notes.insert("1.0", supplier["notes"] or "")

    def save(self) -> bool:
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo(
                "Fournisseur", "Sélectionnez un fournisseur.", parent=self
            )
            return False
        franco_text = self.fields["franco_ht"].get().strip().replace(",", ".")
        minimum_text = (
            self.fields["minimum_order_ht"].get().strip().replace(",", ".")
        )
        try:
            franco = float(franco_text) if franco_text else None
            minimum = float(minimum_text) if minimum_text else None
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
        self.app.sync_team_data()
        return True

    def refresh(self) -> None:
        self.all_suppliers = self.database.list_suppliers(used_only=True)
        self.filter_suppliers()
        self._valid = True


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
            "Importez le nouveau fichier Excel ; les changements sont historisés.",
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
        self.progress = ttk.Progressbar(
            progress_box, mode="determinate", maximum=100
        )
        self.progress.pack(fill="x")
        self.status_label = ttk.Label(
            progress_box,
            text="Sélectionnez la base complète tarifaire.",
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
            columns=("date", "file", "rows", "added", "updated", "missing"),
            show="headings",
            height=10,
        )
        for column, title, width in (
            ("date", "Date", 135),
            ("file", "Fichier", 320),
            ("rows", "Articles", 90),
            ("added", "Ajoutés", 75),
            ("updated", "Modifiés", 75),
            ("missing", "Disparus", 75),
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
        self._shared_manifest: dict[str, object] | None = None

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
        self.path_var.set(
            f"Catalogue partagé : {manifest.get('version', '')}"
        )
        self._start_worker(None, self._shared_manifest)

    def _start_worker(
        self,
        path: Path | None,
        shared_manifest: dict[str, object] | None,
    ) -> None:
        self.import_button.configure(state="disabled")
        self.progress["value"] = 0
        self.worker = threading.Thread(
            target=self._run_import,
            args=(path, shared_manifest),
            daemon=True,
        )
        self.worker.start()
        self.after(100, self._poll_messages)

    def _run_import(
        self,
        path: Path | None,
        shared_manifest: dict[str, object] | None,
    ) -> None:
        try:
            if shared_manifest is not None:
                if not self.app.collaboration:
                    raise CollaborationError(
                        "Le mode collaboratif n'est plus actif."
                    )
                self.messages.put(
                    ("progress", 0, "Vérification du catalogue partagé...")
                )
                path = self.app.collaboration.catalog_source(shared_manifest)
            if path is None:
                raise FileNotFoundError("Catalogue introuvable")
            importer = CatalogImporter(self.database)
            result = importer.import_file(
                path,
                progress=lambda current, total, message: self.messages.put(
                    ("progress", current, message)
                ),
            )
            publication = None
            if shared_manifest is not None and self.app.collaboration:
                self.app.collaboration.mark_catalog_applied(shared_manifest)
                publication = shared_manifest
            elif self.app.collaboration:
                self.messages.put(
                    ("progress", 99, "Publication sur le dossier partagé...")
                )
                publication = self.app.collaboration.publish_catalog(
                    path, result
                )
            self.messages.put(("done", result, publication))
        except Exception as exc:
            self.messages.put(("error", str(exc)))

    def _poll_messages(self) -> None:
        try:
            while True:
                message = self.messages.get_nowait()
                if message[0] == "progress":
                    self.progress["value"] = message[1]
                    self.status_label.configure(text=message[2])
                elif message[0] == "done":
                    self._import_done(message[1], message[2])
                    return
                elif message[0] == "error":
                    self.import_button.configure(state="normal")
                    self.status_label.configure(text="Échec de l'import.")
                    messagebox.showerror("Import CAHPP", message[1], parent=self)
                    return
        except queue.Empty:
            pass
        if self.worker and self.worker.is_alive():
            self.after(100, self._poll_messages)

    def _import_done(
        self,
        result: ImportResult,
        publication: dict[str, object] | None = None,
    ) -> None:
        self.import_button.configure(state="normal")
        self.progress["value"] = 100
        if result.already_imported:
            self.status_label.configure(
                text="Ce fichier avait déjà été importé."
            )
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
            ordered_changes = self.database.ordered_changes_for_import(
                result.import_id
            )
            details = (
                f"{result.row_count:,} articles lus\n"
                f"{result.added_count:,} ajoutés\n"
                f"{result.updated_count:,} modifiés\n"
                f"{result.missing_count:,} absents du nouveau fichier\n"
                f"{len(ordered_changes):,} article(s) déjà commandé(s) modifié(s)"
            ).replace(",", " ")
            messagebox.showinfo("Import CAHPP terminé", details, parent=self)
            if ordered_changes:
                dialog = PriceChangesDialog(self, ordered_changes)
                self.wait_window(dialog)
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
                    format_number(item["row_count"]),
                    format_number(item["added_count"]),
                    format_number(item["updated_count"]),
                    format_number(item["missing_count"]),
                ),
            )
        self._valid = True


class SettingsPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header(
            "Paramètres",
            "Établissement, PDF, préparation des e-mails et sauvegardes.",
        )
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)
        identity = ttk.Frame(notebook, style="Surface.TFrame", padding=18)
        pdf = ttk.Frame(notebook, style="Surface.TFrame", padding=18)
        email = ttk.Frame(notebook, style="Surface.TFrame", padding=18)
        backup = ttk.Frame(notebook, style="Surface.TFrame", padding=18)
        collaboration = ttk.Frame(
            notebook, style="Surface.TFrame", padding=18
        )
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
                ttk.Entry(
                    surface, textvariable=self.vars[key], width=70
                ).grid(row=row, column=1, sticky="ew", padx=(14, 0), pady=7)
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
        self.identity_save_button.grid(
            row=row + 1, column=1, sticky="e", pady=(18, 0)
        )

        row = add_fields(pdf, pdf_fields)
        ttk.Label(
            pdf,
            text="Dossier PDF par défaut",
            style="Surface.TLabel",
        ).grid(row=row, column=0, sticky="w", pady=5)
        self.pdf_directory_var = tk.StringVar()
        pdf_directory_row = ttk.Frame(pdf, style="Surface.TFrame")
        pdf_directory_row.grid(
            row=row, column=1, sticky="ew", padx=(14, 0), pady=5
        )
        ttk.Entry(
            pdf_directory_row, textvariable=self.pdf_directory_var
        ).pack(side="left", fill="x", expand=True)
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
        self.pdf_save_button.grid(
            row=row + 1, column=1, sticky="e", pady=(18, 0)
        )

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
        self.email_body.grid(
            row=row, column=1, sticky="ew", padx=(14, 0), pady=5
        )
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
        self.email_save_button.grid(
            row=row + 2, column=1, sticky="e", pady=(18, 0)
        )

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
        ttk.Label(
            collaboration, text="Nom d'utilisateur", style="Surface.TLabel"
        ).grid(row=2, column=0, sticky="w", pady=7)
        self.user_name_var = tk.StringVar()
        ttk.Entry(
            collaboration, textvariable=self.user_name_var, width=55
        ).grid(row=2, column=1, columnspan=2, sticky="ew", padx=(14, 0), pady=7)
        self.collaboration_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            collaboration,
            text="Activer le mode collaboratif",
            variable=self.collaboration_enabled_var,
        ).grid(
            row=3, column=1, columnspan=2, sticky="w", padx=(14, 0), pady=7
        )
        ttk.Label(
            collaboration, text="Dossier partagé", style="Surface.TLabel"
        ).grid(row=4, column=0, sticky="w", pady=7)
        self.shared_path_var = tk.StringVar()
        ttk.Entry(
            collaboration, textvariable=self.shared_path_var
        ).grid(row=4, column=1, sticky="ew", padx=(14, 0), pady=7)
        ttk.Button(
            collaboration,
            text="Parcourir",
            command=self.browse_shared_directory,
        ).grid(row=4, column=2, sticky="e", padx=(7, 0), pady=7)
        collaboration.columnconfigure(1, weight=1)
        collab_actions = ttk.Frame(
            collaboration, style="Surface.TFrame"
        )
        collab_actions.grid(
            row=5, column=1, columnspan=2, sticky="w", padx=(14, 0), pady=(12, 0)
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
        self.collaboration_status = ttk.Label(
            collaboration,
            text="",
            style="Surface.TLabel",
            wraplength=780,
            justify="left",
        )
        self.collaboration_status.grid(
            row=6,
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
                current
                if current and Path(current).is_dir()
                else str(Path.home())
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
            (
                "Renommage sécurisé : "
                + ("OK" if result.atomic_rename else "Échec")
            ),
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
        values["email_body_template"] = self.email_body.get(
            "1.0", "end"
        ).strip()
        values["pdf_show_page_number"] = (
            "1" if self.show_page_number_var.get() else "0"
        )
        values["user_name"] = user_name
        values["collaboration_enabled"] = (
            "1" if self.collaboration_enabled_var.get() else "0"
        )
        values["shared_workspace_path"] = shared_path
        self.database.save_settings(values)
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
        return True

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
        self.backup_status.configure(
            text=f"Sauvegarde complète créée : {destination}"
        )
        return True

    def refresh(self) -> None:
        settings = self.database.get_settings()
        for key, variable in self.vars.items():
            variable.set(settings.get(key, ""))
        self.logo_var.set(settings.get("logo_path", ""))
        self.pdf_directory_var.set(
            settings.get("pdf_default_directory", "")
        )
        self.email_body.delete("1.0", "end")
        self.email_body.insert(
            "1.0", settings.get("email_body_template", "")
        )
        self.show_page_number_var.set(
            settings.get("pdf_show_page_number", "1") != "0"
        )
        self.user_name_var.set(settings.get("user_name", ""))
        self.shared_path_var.set(settings.get("shared_workspace_path", ""))
        self.collaboration_enabled_var.set(
            settings.get("collaboration_enabled", "0") == "1"
        )
        if self.app.collaboration:
            last_sync = settings.get("collaboration_last_sync_at", "")
            catalogue = settings.get("collaboration_catalog_version", "")
            self.collaboration_status.configure(
                text=(
                    f"Espace : {self.app.collaboration.workspace_id}\n"
                    f"Dernière synchronisation : "
                    f"{format_timestamp(last_sync)}\n"
                    f"Catalogue partagé : {catalogue or 'non publié'}"
                ),
                foreground=COLORS["success"],
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
        self._valid = True
