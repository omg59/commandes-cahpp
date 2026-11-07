"""Application Qt Horizon, exécutée sur un profil isolé de la version stable."""

from __future__ import annotations

import logging
import json
import sys
from datetime import datetime
from functools import partial
from pathlib import Path

from PySide6.QtCore import (
    QLibraryInfo,
    QLocale,
    QProcess,
    QSettings,
    Qt,
    QTimer,
    QTranslator,
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
    QVBoxLayout,
    QWidget,
)

from ..app_logging import configure_logging, install_exception_hooks, log_failure
from ..catalog_importer import CatalogImporter, ImportOptions
from ..database import Database
from ..local_services import create_complete_backup
from ..paths import BACKUP_DIR, DATABASE_PATH, RESOURCE_DIR, ensure_directories
from . import NAME, VERSION
from .bootstrap import resource_root
from .catalog import CatalogPage
from .dialogs import ProductDialog
from .jobs import Jobs
from .orders import OrdersPage, PreparePage
from .overview import OverviewPage, StatisticsPage
from .services import HorizonService, seed_demo
from .theme import apply_theme
from .widgets import button, label

logger = logging.getLogger(__name__)


def inspect_catalog(database, path, *, cancel, progress):
    progress(0, 100, "Analyse et contrôle du fichier CAHPP…")
    return CatalogImporter(database).inspect_file(path)


def apply_catalog(database, path, preview, options, *, cancel, progress):
    if not preview.already_imported:
        progress(0, 100, "Sauvegarde du profil d'essai avant import…")
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
        self.setWindowTitle(f"{NAME} {VERSION} — profil d'essai")
        self.setMinimumSize(900, 600)
        geometry = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1460, geometry.width() - 30), min(930, geometry.height() - 40))
        logo = RESOURCE_DIR / "horizon" / "ladapt.png"
        self.setWindowIcon(QIcon(str(logo)))
        central = QWidget()
        central.setObjectName("canvas")
        self.setCentralWidget(central)
        shell = QHBoxLayout(central)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(196)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(16, 24, 16, 18)
        nav.setSpacing(9)
        picture = label()
        picture.setAlignment(Qt.AlignmentFlag.AlignLeft)
        picture.setPixmap(
            QPixmap(str(logo)).scaled(
                88,
                88,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        nav.addWidget(picture)
        nav.addWidget(label("HORIZON", "brand"))
        nav.addWidget(label("Commandes CAHPP", "brandSub"))
        nav.addSpacing(20)
        self.nav_buttons = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        for key, title in [
            ("overview", "Vue d'ensemble"),
            ("catalog", "Catalogue"),
            ("prepare", "Préparation"),
            ("orders", "Commandes"),
            ("statistics", "Statistiques"),
        ]:
            b = button(title, partial(self.navigate, key), "nav")
            b.setCheckable(True)
            group.addButton(b)
            self.nav_buttons[key] = b
            nav.addWidget(b)
        nav.addStretch()
        nav.addWidget(label("VERSION D'ESSAI", "brandSub"))
        nav.addWidget(label("Alpha 1 · 2.0.0a1", "brandSub"))
        nav.addSpacing(8)
        user = database.get_settings().get("user_name") or "Utilisateur Horizon"
        nav.addWidget(label(user, "brandSub", True))
        shell.addWidget(sidebar)
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
        bar.addWidget(button("Copier une base 1.6…", self.choose_database))
        self.theme_button = button("Changer le thème", self.toggle_theme)
        bar.addWidget(self.theme_button)
        content.addWidget(top)
        self.stack = QStackedWidget()
        content.addWidget(self.stack, 1)
        self.catalog = CatalogPage(self)
        self.prepare = PreparePage(self)
        self.orders = OrdersPage(self)
        self.statistics = StatisticsPage(self)
        self.overview = OverviewPage(self)
        self.pages = {
            "overview": self.overview,
            "catalog": self.catalog,
            "prepare": self.prepare,
            "orders": self.orders,
            "statistics": self.statistics,
        }
        self.containers = {}
        for key, page in self.pages.items():
            wrapper = QWidget()
            layout = QVBoxLayout(wrapper)
            layout.setContentsMargins(22, 23, 22, 22)
            layout.addWidget(page)
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setWidget(wrapper)
            self.stack.addWidget(area)
            self.containers[key] = area
        self.progress = QProgressBar()
        self.progress.hide()
        self.progress.setMaximumWidth(180)
        self.progress.setTextVisible(False)
        self.statusBar().addPermanentWidget(self.progress)
        mode = "Démonstration" if info["mode"] == "demo" else "Copie de travail"
        self.profile_label = label(
            mode + " · profil isolé · collaboration non activée", "muted"
        )
        self.statusBar().addPermanentWidget(self.profile_label)
        self.statistics.reload_suppliers()
        self.navigate("overview")

    def navigate(self, key):
        if self.closing:
            return
        self.stack.setCurrentWidget(self.containers[key])
        self.nav_buttons[key].setChecked(True)
        self.pages[key].refresh()

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
        apply_theme(QApplication.instance(), dark)
        self.settings.setValue("dark", dark)
        for chart in (self.overview.chart, self.statistics.line, self.statistics.bars):
            chart.update()

    def data_changed(self):
        self.statistics.reload_suppliers()
        current = self.stack.currentWidget()
        for key, page in self.pages.items():
            if self.containers[key] is current:
                page.refresh()

    def new_order(self):
        if self.allow_discard_or_save():
            self.prepare.reset()
            self.navigate("prepare")

    def allow_discard_or_save(self):
        if not self.prepare.cart.dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Préparation non enregistrée",
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

    def add_product(self, p):
        if self.import_busy:
            self.notify("Attendez la fin de l’import avant d’ajouter un article.")
            return
        p = self.database.get_product(p["id"])
        if p["catalog_review_required"]:
            dialog = ProductDialog(self.database, p["id"], self)
            if not dialog.exec():
                return
            p = self.database.get_product(p["id"])
        try:
            if self.prepare.add(p):
                self.navigate("prepare")
                self.notify("Un carton ajouté à la préparation.")
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
                "Créer un profil d'essai",
                "Horizon va créer une copie indépendante de cette base et l'ouvrir dans une nouvelle fenêtre. Les documents historiques ne sont pas recopiés. Continuer ?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        args = ["--copy-database", source]
        if not getattr(sys, "frozen", False):
            args = [str(resource_root() / "main_horizon.py"), *args]
        ok, _ = QProcess.startDetached(sys.executable, args)
        if not ok:
            self.report_error("Le nouveau profil n'a pas pu être lancé.")
        else:
            self.notify("Ouverture d'un nouveau profil d'essai à partir de la copie.")

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
            f"{title}\n{preview.row_count:,} lignes\nMois : {preview.period or 'non précisé'}\n\n".replace(
                ",", " "
            )
            + "\n\n".join(preview.warnings)
        )
        message += "\n\nAppliquer dans le profil d'essai Horizon ? Une sauvegarde sera créée avant tout nouvel import."
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
            partial(apply_catalog, self.database, path, preview, options),
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
        self.close()


def create_application(argv=None):
    app = QApplication.instance() or QApplication(argv or sys.argv[:1])
    app.setApplicationName("Commandes CAHPP Horizon")
    app.setOrganizationName("Commandes CAHPP")
    QLocale.setDefault(QLocale(QLocale.Language.French, QLocale.Country.France))
    translator = QTranslator(app)
    if translator.load(
        QLocale("fr_FR"),
        "qtbase",
        "_",
        QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath),
    ):
        app.installTranslator(translator)
    app.horizon_translator = translator
    return app


def run(profile, info):
    ensure_directories()
    configure_logging()
    install_exception_hooks()
    app = create_application()
    database = Database(DATABASE_PATH)
    settings = database.get_settings()
    database.set_current_user(
        settings.get("user_id") or "horizon-test",
        settings.get("user_name") or "Utilisateur Horizon",
    )
    database.save_settings({"collaboration_enabled": "0"})
    if info["mode"] == "demo":
        seed_demo(database)
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
                and (RESOURCE_DIR / "horizon" / "ladapt.png").is_file()
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
