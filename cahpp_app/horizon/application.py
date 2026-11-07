"""Application Qt Horizon, exécutée sur un profil isolé de la version stable."""

from __future__ import annotations

import logging
import json
import sys
from datetime import datetime
from functools import partial
from pathlib import Path

from PySide6.QtCore import (
    QProcess,
    QProcessEnvironment,
    QSettings,
    Qt,
    QTimer,
)
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..app_logging import configure_logging, install_exception_hooks, log_failure
from ..catalog_importer import CatalogImporter, ImportOptions
from ..database import Database
from ..local_services import create_complete_backup
from ..paths import BACKUP_DIR, DATABASE_PATH, ensure_directories
from . import NAME, VERSION
from .bootstrap import resource_root, profile_launch_command
from .catalog import CatalogPage
from .dialogs import ProductDialog
from .jobs import Jobs
from .orders import OrdersPage, PreparePage
from .overview import OverviewPage, StatisticsPage
from .services import HorizonService
from .theme import apply_theme
from .widgets import button, label, ThemeSwitch
from .operations import Operations, months_before
from .settings import SettingsPage, DiagnosticDialog
from .suppliers import SuppliersPage, SuggestionsPage
from .forms import action
from .qt_runtime import create_application
from .dates import format_month

logger = logging.getLogger(__name__)


def inspect_catalog(database, path, *, cancel, progress):
    progress(0, 100, "Analyse et contrôle du fichier CAHPP…")
    return CatalogImporter(database).inspect_file(path)


def apply_catalog(database, path, preview, options, *, cancel, progress):
    if not preview.already_imported:
        progress(0, 100, "Sauvegarde du profil de travail avant import…")
        destination = BACKUP_DIR / (
            "horizon-avant-import-"
            + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            + ".zip"
        )
        temporary = destination.with_name("." + destination.name)
        try:
            create_complete_backup(database, temporary)
            temporary.replace(destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    progress(2, 100, "Vérification de l'import…")
    return CatalogImporter(database).import_file(
        path, progress=progress, options=options, preview=preview
    )


class HorizonWindow(QMainWindow):
    def __init__(self, database, profile, info):
        super().__init__()
        self.database = database
        self.profile = Path(profile)
        self.info = info
        self.service = HorizonService(database)
        self.operations = Operations(database)
        self.sync_running = False
        self.shared_manifest = None
        self.catalog_prompted = ""
        self.jobs = Jobs(self)
        self.jobs.progress.connect(self.work_progress)
        self.import_busy = False
        self.closing = False
        self.close_ready = False
        self.settings = QSettings(
            str(self.profile / "interface.ini"), QSettings.Format.IniFormat
        )
        apply_theme(
            QApplication.instance(), self.settings.value("dark", False, type=bool)
        )
        self.profile_name = (
            database.get_settings().get("establishment_name")
            or info.get("display_name")
            or "Profil principal"
        )
        self.setWindowTitle(f"{NAME} {VERSION} — {self.profile_name}")
        self.setMinimumSize(900, 600)
        geometry = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1460, geometry.width() - 30), min(930, geometry.height() - 40))
        logo = resource_root() / "assets" / "app_icon.png"
        self.setWindowIcon(QIcon(str(resource_root() / "assets" / "app_icon.ico")))
        central = QWidget()
        central.setObjectName("canvas")
        self.setCentralWidget(central)
        shell = QHBoxLayout(central)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(196)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(16, 24, 16, 18)
        nav.setSpacing(9)
        picture = label()
        self.brand_logo = picture
        picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        picture.setPixmap(
            QPixmap(str(logo)).scaled(
                88,
                88,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        nav.addWidget(picture)
        for text, style in [("HORIZON", "brand"), ("Commandes CAHPP", "brandSub")]:
            brand = label(text, style)
            brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
            nav.addWidget(brand)
        nav.addSpacing(20)
        self.nav_buttons = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        for key, title in [
            ("overview", "Vue d'ensemble"),
            ("catalog", "Catalogue"),
            ("commands", "Commandes"),
            ("statistics", "Statistiques"),
            ("imports", "Mise à jour CAHPP"),
            ("settings", "Paramètres"),
        ]:
            b = button(title, partial(self.navigate, key), "nav")
            b.setCheckable(True)
            group.addButton(b)
            self.nav_buttons[key] = b
            nav.addWidget(b)
        nav.addStretch()
        nav.addWidget(label("VERSION BÊTA", "brandSub"))
        nav.addWidget(label(VERSION, "brandSub"))
        nav.addSpacing(8)
        user = database.get_settings().get("user_name") or "Utilisateur Horizon"
        nav.addWidget(label(user, "brandSub", True))
        nav.addSpacing(10)
        self.ladapt_logo = label()
        self.ladapt_logo.setAccessibleName("Logo LADAPT")
        self.ladapt_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ladapt_logo.setPixmap(
            QPixmap(str(resource_root() / "ressources/horizon/ladapt.png")).scaled(
                112,
                112,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        nav.addWidget(self.ladapt_logo)
        sidebar_area = QScrollArea()
        sidebar_area.setFixedWidth(212)
        sidebar_area.setWidgetResizable(True)
        sidebar_area.setFrameShape(QFrame.Shape.NoFrame)
        sidebar_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sidebar_area.setWidget(sidebar)
        shell.addWidget(sidebar_area)
        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        shell.addLayout(content, 1)
        top = QFrame()
        top.setObjectName("topbar")
        bar = QHBoxLayout(top)
        bar.setContentsMargins(22, 13, 22, 13)
        self.global_search = QLineEdit()
        self.global_search.setPlaceholderText("Rechercher dans le catalogue…")
        self.global_search.setAccessibleName("Recherche rapide")
        self.global_search.returnPressed.connect(self.global_find)
        bar.addWidget(self.global_search, 1)
        self.theme_switch = ThemeSwitch()
        self.theme_switch.setChecked(
            bool(QApplication.instance().property("horizonDark"))
        )
        self.theme_switch.toggled.connect(self.set_dark_theme)
        bar.addWidget(self.theme_switch)
        content.addWidget(top)
        self.stack = QStackedWidget()
        content.addWidget(self.stack, 1)
        self.catalog = CatalogPage(self)
        self.prepare = PreparePage(self)
        self.orders = OrdersPage(self)
        self.statistics = StatisticsPage(self)
        self.overview = OverviewPage(self)
        self.suppliers = SuppliersPage(self)
        self.preferences = SettingsPage(self)
        self.suggestions = SuggestionsPage(self)
        from .imports import ImportsPage

        self.imports = ImportsPage(self)
        self.pages = {
            "overview": self.overview,
            "catalog": self.catalog,
            "prepare": self.prepare,
            "orders": self.orders,
            "statistics": self.statistics,
            "settings": self.preferences,
            "suggestions": self.suggestions,
            "imports": self.imports,
        }
        self.containers = {}
        self.command_keys = ("prepare", "orders", "suggestions")
        self.command_tabs = QTabWidget()
        self.command_tabs.setAccessibleName("Parcours de commande")
        commands = QWidget()
        commands_layout = QVBoxLayout(commands)
        commands_layout.setContentsMargins(22, 23, 22, 22)
        commands_layout.addWidget(self.command_tabs)
        self.containers["commands"] = commands
        self.stack.addWidget(commands)
        for key, page in self.pages.items():
            wrapper = QWidget()
            layout = QVBoxLayout(wrapper)
            layout.setContentsMargins(
                *((14, 14, 14, 14) if key in self.command_keys else (22, 23, 22, 22))
            )
            layout.addWidget(page)
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setWidget(wrapper)
            if key not in self.command_keys:
                self.stack.addWidget(area)
            self.containers[key] = area
        for key, title in zip(
            self.command_keys,
            ("Nouvelle commande", "Suivi des commandes", "À recommander"),
        ):
            self.command_tabs.addTab(self.containers[key], title)
        self.command_tabs.currentChanged.connect(self.command_tab_changed)
        self.progress = QProgressBar()
        self.progress.hide()
        self.progress.setMaximumWidth(180)
        self.progress.setTextVisible(False)
        self.statusBar().addPermanentWidget(self.progress)
        self.profile_label = label(self.profile_name + " · profil local", "muted")
        self.statusBar().addPermanentWidget(self.profile_label)
        self.statistics.reload_suppliers()
        self.navigate("overview")
        self.sync_timer = QTimer(self)
        self.sync_timer.timeout.connect(self.sync_collaboration)
        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.setInterval(30000)
        self.heartbeat_timer.timeout.connect(self.heartbeat)
        self.heartbeat_timer.start()
        self.configure_sync_timer()
        QTimer.singleShot(250, self.sync_collaboration)
        if self.operations.last_sync_error:
            QTimer.singleShot(
                300,
                lambda: self.notify(
                    "Partage indisponible : la consultation et les diagnostics restent accessibles."
                ),
            )
        if info.get("missing_files"):
            QTimer.singleShot(
                500,
                lambda: self.notify(
                    f"Copie terminée : {info.get('missing_files')} document(s) source indisponible(s)."
                ),
            )
        QTimer.singleShot(1200, self.background_maintenance)
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def navigate(self, key):
        if self.closing:
            return
        if key == "suppliers":
            self.navigate("settings")
            self.preferences.tabs.setCurrentWidget(self.suppliers)
            self.suppliers.refresh()
            return
        if key in self.command_keys:
            self.command_tabs.blockSignals(True)
            self.command_tabs.setCurrentWidget(self.containers[key])
            self.command_tabs.blockSignals(False)
            key = "commands"
        self.stack.setCurrentWidget(self.containers[key])
        self.nav_buttons[key].setChecked(True)
        self.refresh_current_page()

    def current_page(self):
        current = self.stack.currentWidget()
        if current is self.containers["commands"]:
            current = self.command_tabs.currentWidget()
        return next(
            (
                page
                for key, page in self.pages.items()
                if self.containers[key] is current
            ),
            None,
        )

    def refresh_current_page(self):
        page = self.current_page()
        if page is not None:
            page.refresh()

    def command_tab_changed(self):
        if self.stack.currentWidget() is self.containers["commands"]:
            self.refresh_current_page()

    def notify(self, text):
        self.statusBar().showMessage(text, 7000)

    def report_error(self, error):
        if self.closing:
            return
        if isinstance(error, BaseException):
            log_failure(logger, "horizon_interface_echec", error)
        QMessageBox.warning(self, "Horizon", str(error))

    def global_find(self):
        self.catalog.browser.query.setText(self.global_search.text())
        self.catalog.browser.filter.setCurrentIndex(0)
        self.navigate("catalog")

    def toggle_theme(self):
        dark = not QApplication.instance().property("horizonDark")
        self.set_dark_theme(dark)

    def set_dark_theme(self, dark):
        apply_theme(QApplication.instance(), dark)
        self.theme_switch.blockSignals(True)
        self.theme_switch.setChecked(dark)
        self.theme_switch.blockSignals(False)
        self.theme_switch.describe(dark)
        self.settings.setValue("dark", dark)
        for chart in (self.overview.chart, self.statistics.line, self.statistics.bars):
            chart.update()

    def data_changed(self):
        self.statistics.reload_suppliers()
        self.refresh_current_page()
        self.sync_collaboration()

    def new_order(self):
        if self.allow_discard_or_save():
            self.prepare.reset()
            self.navigate("prepare")

    def allow_discard_or_save(self):
        if not self.prepare.cart.dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Commande non enregistrée",
            "Enregistrer le brouillon avant de poursuivre ?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self.prepare.save_draft()
        return True

    @action
    def add_product(self, p, quantity=None):
        if self.import_busy:
            self.notify("Attendez la fin de l’import avant d’ajouter un article.")
            return
        p = self.database.get_product(p["id"])
        if p["catalog_review_required"]:
            with self.operations.locked_product(p["id"]):
                dialog = ProductDialog(self.database, p["id"], self)
                if not dialog.exec():
                    return
            p = self.database.get_product(p["id"])
        try:
            if self.prepare.add(p, quantity=quantity):
                self.navigate("prepare")
                self.notify("Article ajouté à la préparation.")
        except ValueError as exc:
            self.report_error(exc)

    def open_orders(self, group="Toutes"):
        self.orders.filter.setCurrentText(group)
        self.navigate("orders")

    def open_order(self, oid):
        self.orders.selected_id = oid
        self.orders.filter.setCurrentIndex(0)
        self.navigate("orders")

    def choose_database(self):
        source, _ = QFileDialog.getOpenFileName(
            self,
            "Créer une copie de votre base CAHPP",
            "",
            "Bases SQLite (*.sqlite3 *.db);;Tous les fichiers (*)",
        )
        if not source:
            return
        if (
            QMessageBox.question(
                self,
                "Importer une base CAHPP",
                "Horizon va créer une copie indépendante de la base et des documents accessibles, puis l'ouvrir dans une nouvelle fenêtre. La source reste inchangée. Continuer ?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.launch_profile(["--copy-database", source])

    def choose_profile(self):
        self.launch_profile(["--choose-profile"])

    def launch_profile(self, arguments):
        program, args = profile_launch_command(arguments)
        process = QProcess(self)
        environment = QProcessEnvironment.systemEnvironment()
        if getattr(sys, "frozen", False):
            environment.insert("PYINSTALLER_RESET_ENVIRONMENT", "1")
        process.setProcessEnvironment(environment)
        process.setProgram(program)
        process.setArguments(args)
        ok, _ = process.startDetached()
        if not ok:
            self.report_error("Le nouveau profil n'a pas pu être lancé.")
        else:
            self.notify(
                "Le choix du profil s'ouvre dans une nouvelle fenêtre. Ce profil reste accessible ici."
            )

    def choose_catalog(self):
        if self.import_busy:
            self.notify("Un import est déjà en cours.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Importer un fichier CAHPP dans Horizon",
            "",
            "Classeurs Excel (*.xlsx)",
        )
        if not path:
            return
        self.shared_manifest = None
        self.start_catalog(path)

    def start_catalog(self, path, shared_manifest=None):
        if self.import_busy or self.sync_running:
            self.notify("Attendez la fin de l'opération en cours.")
            return
        self.shared_manifest = shared_manifest
        self.import_busy = True
        self.progress.setRange(0, 0)
        self.progress.show()
        self.jobs.submit(
            "catalog-inspect",
            partial(inspect_catalog, self.database, Path(path)),
            partial(self.catalog_preview, Path(path)),
        )

    def catalog_preview(self, path, preview, error):
        if error:
            self.end_import()
            self.report_error(error)
            return
        title = {
            "full": "Catalogue complet",
            "delta": "Évolutions mensuelles",
            "snapshot": "Catalogue partagé complet",
        }[preview.mode]
        message = (
            f"{title}\n{preview.row_count:,} lignes\nMois : {format_month(preview.period) or 'non précisé'}\n\n".replace(
                ",", " "
            )
            + "\n\n".join(preview.warnings)
        )
        message += "\n\nAppliquer dans le profil Horizon ? Une sauvegarde sera créée avant tout nouvel import."
        if (
            QMessageBox.question(self, "Vérifier l'import CAHPP", message)
            != QMessageBox.StandardButton.Yes
        ):
            self.end_import()
            return
        options = ImportOptions(
            confirm_baseline="baseline" in preview.confirmations,
            allow_revision="revision" in preview.confirmations,
            confirm_full_replacement="replacement" in preview.confirmations,
            confirm_snapshot_replacement="snapshot_replacement"
            in preview.confirmations,
        )
        self.progress.setRange(0, 100)
        self.jobs.submit(
            "catalog-import",
            partial(
                self.operations.import_catalog,
                path,
                preview,
                options,
                shared_manifest=self.shared_manifest,
            ),
            self.catalog_applied,
        )

    def work_progress(self, key, percent, text):
        if key.startswith("catalog-"):
            self.progress.setValue(percent)
            self.statusBar().showMessage(text)

    def end_import(self):
        self.import_busy = False
        self.progress.hide()
        self.statusBar().clearMessage()

    def catalog_applied(self, result, error):
        self.end_import()
        if error:
            self.report_error(error)
            return
        self.data_changed()
        QMessageBox.information(
            self,
            "Import terminé",
            f"{result.row_count} articles lus\n{result.added_count} ajoutés\n{result.updated_count} modifiés\n{result.deactivated_count} retirés\n{result.review_count} articles à vérifier\n\n"
            + (
                "Ce fichier avait déjà été appliqué."
                if result.already_imported
                else "Le profil Horizon est mis à jour."
            ),
        )

    def closeEvent(self, event):
        if self.close_ready:
            self.settings.setValue("geometry", self.saveGeometry())
            self.settings.sync()
            event.accept()
            return
        if self.closing:
            event.ignore()
            return
        if not self.allow_discard_or_save():
            event.ignore()
            return
        for page in (self.preferences, self.suppliers):
            if page.has_unsaved_changes():
                answer = QMessageBox.question(
                    self,
                    "Saisie non enregistrée",
                    "Enregistrer les modifications avant de fermer ?",
                    QMessageBox.StandardButton.Save
                    | QMessageBox.StandardButton.Discard
                    | QMessageBox.StandardButton.Cancel,
                )
                if answer == QMessageBox.StandardButton.Cancel or (
                    answer == QMessageBox.StandardButton.Save and not page.save()
                ):
                    event.ignore()
                    return
        if (
            self.import_busy
            and QMessageBox.question(
                self,
                "Import en cours",
                "Annuler l'opération en cours et fermer Horizon ?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            event.ignore()
            return
        self.closing = True
        self.sync_timer.stop()
        self.heartbeat_timer.stop()
        self.jobs.close()
        self.catalog.browser.timer.stop()
        self.prepare.browser.timer.stop()
        event.ignore()
        self.setEnabled(False)
        QTimer.singleShot(30, self.finish_close)

    def finish_close(self):
        if self.jobs.busy:
            QTimer.singleShot(50, self.finish_close)
            return
        self.close_ready = True
        self.operations.close()
        self.close()
        path = getattr(self, "pending_installer_path", None)
        if path:
            QProcess.startDetached(path, [])

    def configure_sync_timer(self):
        settings = self.database.get_settings()
        interval = max(15, min(600, int(settings.get("sync_interval_seconds", "60"))))
        self.sync_timer.start(interval * 1000)

    def dirty_forms(self):
        return any(
            page.has_unsaved_changes() for page in (self.preferences, self.suppliers)
        )

    def sync_collaboration(self, force=False):
        if (
            self.closing
            or not self.operations.manager
            or self.sync_running
            or self.import_busy
        ):
            return
        if (
            self.dirty_forms()
            and self.database.get_settings().get("pause_sync_while_editing", "1") != "0"
        ):
            self.profile_label.setText(
                "Synchronisation en pause · saisie non enregistrée"
            )
            return
        self.sync_running = True
        self.profile_label.setText("Synchronisation…")

        def done(result, error):
            self.sync_running = False
            if error:
                self.profile_label.setText("Partage indisponible · voir le diagnostic")
                if force:
                    self.report_error(error)
                return
            conflicts = (result.get("orders") or {}).get("conflicts", 0)
            self.profile_label.setText(
                f"Synchronisé · {datetime.now():%H:%M}"
                + (f" · {conflicts} conflit(s) à examiner" if conflicts else "")
            )
            self.statistics.reload_suppliers()
            self.refresh_current_page()
            if result.get("catalog_pending"):
                self.imports.refresh()
            self.check_shared_updates()

        self.jobs.submit("collaboration", self.operations.sync, done)

    def check_shared_updates(self):
        settings = self.database.get_settings()

        def work(*, cancel, progress):
            return self.operations.pending_installer(
                VERSION, settings.get("horizon_dismissed_installer_version", "")
            )

        def done(installer, error):
            if error or not installer or self.closing:
                return
            answer = QMessageBox.question(
                self,
                "Mise à jour Horizon disponible",
                "La version "
                + installer["version"]
                + " est disponible dans le partage. Fermer Horizon et lancer son installation ?",
            )
            if answer == QMessageBox.StandardButton.Yes:
                if self.allow_discard_or_save():
                    self.pending_installer_path = installer["path"]
                    self.close()
                    if not self.closing:
                        self.pending_installer_path = None
            else:
                self.database.save_settings(
                    {"horizon_dismissed_installer_version": installer["version"]}
                )

        self.jobs.submit("shared-installer", work, done)

    def heartbeat(self):
        if not self.operations.manager or self.closing:
            return

        def work(*, cancel, progress):
            with self.operations.guard:
                if self.operations.manager:
                    self.operations.manager.refresh_active_locks()

        self.jobs.submit(
            "heartbeat",
            work,
            lambda result, error: self.notify(str(error)) if error else None,
        )

    def open_diagnostics(self):
        dialog = DiagnosticDialog(self)
        dialog.exec()

    def background_maintenance(self):
        if self.closing or self.import_busy or self.sync_running:
            return
        from datetime import date, timedelta

        settings = self.database.get_settings()
        now = datetime.now()

        def due(key, days):
            try:
                return (
                    datetime.fromisoformat(settings.get(key, ""))
                    + timedelta(days=int(days))
                    < now
                )
            except ValueError:
                return True

        if due("last_backup_at", settings.get("backup_reminder_days", "14")):
            self.notify(
                "Une sauvegarde complète est recommandée : Paramètres → Maintenance."
            )
        if due("last_integrity_check_at", settings.get("integrity_check_days", "7")):
            self.preferences.integrity()
        if settings.get("automatic_archive_enabled") == "1":
            before = months_before(
                date.today(), int(settings.get("archive_after_months", "24"))
            )
            self.preferences.maintenance(
                "automatic-archive",
                partial(self.database.archive_old_orders, before),
                lambda result: (
                    self.notify(f"{len(result)} commande(s) archivée(s).")
                    if result
                    else None
                ),
            )


def run(profile, info):
    ensure_directories()
    configure_logging()
    install_exception_hooks()
    app = create_application()
    new_database = not DATABASE_PATH.is_file()
    database = Database(DATABASE_PATH)
    if new_database:
        database.save_settings(
            {
                "establishment_name": info.get("display_name") or "",
                "user_name": info.get("initial_user_name") or "Utilisateur",
            }
        )
    settings = database.get_settings()
    database.set_current_user(
        settings.get("user_id") or "",
        settings.get("user_name") or "Utilisateur Horizon",
    )
    window = HorizonWindow(database, profile, info)
    window.show()
    app.aboutToQuit.connect(window.jobs.close)
    if info.get("smoke_test"):

        def probe():
            if window.jobs.tasks:
                QTimer.singleShot(50, probe)
                return
            ready = (
                window.overview.metrics[0].value.text() != "—"
                and (resource_root() / "assets" / "app_icon.png").is_file()
                and not window.ladapt_logo.pixmap().isNull()
                and all(
                    (resource_root() / path).is_file()
                    for path in (
                        "ressources/horizon/NOTICE.txt",
                        "ressources/horizon/LGPL-3.0.txt",
                        "ressources/horizon/GPL-3.0.txt",
                        "ressources/DEJAVU-LICENSE.txt",
                    )
                )
            )
            if ready:
                (profile / "startup-ok.json").write_text(
                    json.dumps(
                        {
                            "version": VERSION,
                            "profile": info["mode"],
                            "qt_translated": bool(app.horizon_translator.filePath()),
                        }
                    ),
                    encoding="utf-8",
                )
                window.prepare.cart.dirty = False
                window.close()
            else:
                window.jobs.close()
                app.exit(2)

        QTimer.singleShot(150, probe)
        QTimer.singleShot(25000, lambda: app.exit(2))
    return app.exec()
