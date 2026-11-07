"""Réglages métier, collaboration et diagnostic Qt complet."""

from datetime import date, datetime
from functools import partial
from pathlib import Path

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import QUrl, qVersion
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..collaboration import CollaborationManager
from ..diagnostics import build_diagnostic_report
from ..local_services import (
    MAIL_TEMPLATE_VARIABLES,
    create_complete_backup,
    portable_path,
)
from ..numbers import parse_decimal
from ..paths import BACKUP_DIR
from ..app_logging import LOG_DIR
from . import VERSION
from .forms import Fields, action
from .operations import months_before
from .widgets import button, label
from .dates import format_datetime
from .about import AboutPage


class DiagnosticDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.report = ""
        self.key = f"diagnostic-{id(self)}"
        self.setWindowTitle("Diagnostic et débogage Horizon")
        self.resize(1000, 720)
        layout = QVBoxLayout(self)
        layout.addWidget(label("Diagnostic et débogage", "heading"))
        self.status = label("", "muted", True)
        layout.addWidget(self.status)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setAccessibleName("Rapport de diagnostic")
        layout.addWidget(self.text, 1)
        row = QHBoxLayout()
        self.refresh_button = button("Actualiser le diagnostic", self.run)
        self.repair_button = button("Reconstruire l'index", self.repair)
        self.copy_button = button("Copier le rapport", self.copy)
        self.export_button = button("Exporter le rapport…", self.export)
        for b in [
            self.refresh_button,
            self.repair_button,
            self.copy_button,
            self.export_button,
        ]:
            row.addWidget(b)
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(
            button(
                "Ouvrir les journaux",
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(LOG_DIR))),
            )
        )
        row.addStretch()
        row.addWidget(button("Fermer", self.reject))
        layout.addLayout(row)
        self.finished.connect(lambda: window.jobs.cancel(self.key))
        self.run()

    def build(self, *, cancel, progress):
        with self.window.operations.guard:
            op = self.window.operations
            report = build_diagnostic_report(
                self.window.database,
                op.manager,
                VERSION,
                op.last_sync_result,
                op.last_sync_error,
                gui_runtime=f"Interface : Horizon / Qt {qVersion()} / PySide6 {pyside_version}",
            )
            return (
                report
                + f"\n\nHORIZON\n-------\nProfil : {self.window.profile}\nMode : {self.window.info.get('mode', '')}\nTâches au déclenchement : {self.task_count}\nImport en cours : {self.import_running}\n"
            )

    def busy(self, value, message=""):
        self.status.setText(message)
        self.refresh_button.setEnabled(not value)
        self.repair_button.setEnabled(not value)
        self.copy_button.setEnabled(bool(self.report))
        self.export_button.setEnabled(bool(self.report))

    def run(self):
        self.task_count = len(self.window.jobs.tasks)
        self.import_running = self.window.import_busy
        self.busy(True, "Contrôles SQLite, index, performances et partage en cours…")
        self.window.jobs.submit(self.key, self.build, self.result)

    def result(self, report, error):
        if error:
            self.report = (
                self.report
                + f"\n\nÉchec du diagnostic : {type(error).__name__}: {error}"
            ).strip()
        else:
            self.report = report or "Aucun résultat."
        self.text.setPlainText(self.report)
        self.busy(
            False,
            "Rapport disponible. Il contient les chemins et le profil, sans le détail des commandes ni les tarifs.",
        )

    def repair(self):
        if (
            QMessageBox.question(
                self,
                "Reconstruire l'index",
                "Reconstruire uniquement l'index de recherche local ? Les articles et les commandes sont conservés.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.busy(True, "Reconstruction et validation de l'index en arrière-plan…")

        def work(*, cancel, progress):
            with self.window.operations.guard:
                self.window.database.rebuild_search(manual=True)
                return True

        def finished(result, error):
            if error:
                self.window.report_error(error)
            self.run()

        self.window.jobs.submit(self.key, work, finished)

    def copy(self):
        QApplication.clipboard().setText(self.report)
        self.status.setText("Rapport copié.")

    @action
    def export(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exporter le diagnostic",
            f"diagnostic-horizon-{datetime.now():%Y%m%d-%H%M%S}.txt",
            "Texte (*.txt)",
        )
        if path:
            Path(path).write_text(self.report, encoding="utf-8")
            self.status.setText("Rapport exporté : " + path)


class SettingsPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.baseline = None
        self.fields = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        header.addWidget(label("Paramètres", "title"), 1)
        self.choose_profile_button = button("Changer de profil…", window.choose_profile)
        header.addWidget(self.choose_profile_button)
        layout.addLayout(header)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        definitions = [
            (
                "Établissement",
                [
                    ("Nom de l'établissement", "establishment_name"),
                    ("Sous-titre / service", "establishment_subtitle"),
                    ("Adresse — ligne 1", "address_line1"),
                    ("Adresse — ligne 2", "address_line2"),
                    ("Code postal et ville", "postal_city"),
                    ("Téléphone", "phone"),
                    ("E-mail", "email"),
                    ("FINESS", "finess"),
                    ("SIRET", "siret"),
                    ("Code APE", "ape"),
                    ("Logo", "logo_path"),
                ],
            ),
            (
                "PDF",
                [
                    ("Titre", "pdf_title"),
                    ("Pied de page", "pdf_footer_text"),
                    ("Dossier PDF par défaut", "pdf_default_directory"),
                    ("Numéros de page", "pdf_show_page_number"),
                ],
            ),
            (
                "E-mail",
                [
                    ("Objet", "email_subject_template"),
                    ("Corps du message", "email_body_template"),
                    ("Adresse de composition", "mail_compose_url"),
                ],
            ),
            (
                "Collaboration",
                [
                    ("Votre nom", "user_name"),
                    ("Activer la collaboration", "collaboration_enabled"),
                    ("Dossier partagé", "shared_workspace_path"),
                    (
                        "Intervalle de synchronisation (secondes)",
                        "sync_interval_seconds",
                    ),
                    (
                        "Pause pendant une saisie non enregistrée",
                        "pause_sync_while_editing",
                    ),
                ],
            ),
            (
                "Maintenance",
                [
                    ("Rappel de sauvegarde (jours)", "backup_reminder_days"),
                    ("Contrôle d'intégrité (jours)", "integrity_check_days"),
                    ("Archivage automatique", "automatic_archive_enabled"),
                    ("Archiver après (mois)", "archive_after_months"),
                    ("Rappel de confirmation (jours)", "confirmation_reminder_days"),
                    ("Rappel de livraison (jours)", "delivery_reminder_days"),
                ],
            ),
        ]
        checks = {
            "pdf_show_page_number",
            "collaboration_enabled",
            "pause_sync_while_editing",
            "automatic_archive_enabled",
        }
        for title, definitions in definitions:
            page = QWidget()
            body = QVBoxLayout(page)
            fields = Fields(body)
            for text, key in definitions:
                fields.add(
                    text,
                    key,
                    check=key in checks,
                    multiline=key == "email_body_template",
                )
            self.fields.append(fields)
            if title == "Établissement":
                body.addWidget(
                    button("Choisir un logo…", partial(self.browse_file, "logo_path"))
                )
            elif title == "PDF":
                body.addWidget(
                    button(
                        "Choisir le dossier PDF…",
                        partial(self.browse_directory, "pdf_default_directory"),
                    )
                )
            elif title == "E-mail":
                body.addWidget(
                    label(
                        "Expressions disponibles : "
                        + " · ".join(
                            "{" + key + "}" for key in MAIL_TEMPLATE_VARIABLES
                        ),
                        "muted",
                        True,
                    )
                )
            elif title == "Collaboration":
                row = QHBoxLayout()
                for text, callback in [
                    (
                        "Choisir le partage…",
                        partial(self.browse_directory, "shared_workspace_path"),
                    ),
                    ("Tester l'accès", self.test_share),
                    ("Synchroniser maintenant", self.sync),
                    ("Ouvrir le partage", self.open_share),
                ]:
                    row.addWidget(button(text, callback))
                body.addLayout(row)
                body.addWidget(
                    label(
                        "La base SQLite reste locale. L'activation du partage et son dossier sont propres à ce profil.",
                        "muted",
                        True,
                    )
                )
            elif title == "Maintenance":
                row = QHBoxLayout()
                for text, callback in [
                    ("Sauvegarde complète…", self.backup),
                    ("Contrôler l'intégrité", self.integrity),
                    ("Archiver maintenant", self.archive),
                ]:
                    row.addWidget(button(text, callback))
                body.addLayout(row)
                body.addWidget(
                    label("Importer les données d'une version 1.6", "heading")
                )
                body.addWidget(
                    label(
                        "Copier le catalogue, les commandes, les fournisseurs et les réglages de votre établissement dans un profil Horizon indépendant.",
                        "muted",
                        True,
                    )
                )
                self.copy_database_button = button(
                    "Importer une base CAHPP 1.6…", window.choose_database
                )
                body.addWidget(self.copy_database_button)
            body.addStretch()
            self.tabs.addTab(page, title)
            if title == "Établissement":
                self.tabs.addTab(window.suppliers, "Fournisseurs")
        self.about = AboutPage(window)
        self.tabs.addTab(self.about, "À propos")
        row = QHBoxLayout()
        self.save_button = button("Enregistrer les paramètres", self.save, "primary")
        row.addWidget(self.save_button)
        row.addWidget(button("Diagnostics et débogage", window.open_diagnostics))
        row.addStretch()
        layout.addLayout(row)
        self.status = label("", "muted", True)
        layout.addWidget(self.status)
        self.tabs.currentChanged.connect(self.tab_changed)

    def tab_changed(self):
        suppliers_selected = self.tabs.currentWidget() is self.window.suppliers
        self.save_button.setVisible(
            not suppliers_selected and self.tabs.currentWidget() is not self.about
        )
        if suppliers_selected:
            self.window.suppliers.refresh()

    def widget(self, key):
        return next(f.widgets[key] for f in self.fields if key in f.widgets)

    def values(self):
        return {
            key: value
            for fields in self.fields
            for key, value in fields.values().items()
        }

    def has_unsaved_changes(self):
        return self.baseline is not None and self.values() != self.baseline

    def refresh(self):
        if self.tabs.currentWidget() is self.window.suppliers:
            self.window.suppliers.refresh()
        if self.has_unsaved_changes():
            return
        settings = self.window.database.get_settings()
        for fields in self.fields:
            fields.load(settings)
        self.baseline = self.values()
        op = self.window.operations
        self.status.setText(
            ("Collaboration active" if op.manager else "Mode local")
            + " · Dernière synchronisation : "
            + (format_datetime(settings.get("collaboration_last_sync_at")) or "jamais")
            + "\nDernière sauvegarde : "
            + (format_datetime(settings.get("last_backup_at")) or "jamais")
            + " · Intégrité : "
            + (settings.get("last_integrity_check_result") or "à contrôler")
        )

    @action
    def save(self):
        values = self.values()
        if not values["user_name"]:
            raise ValueError("Votre nom est obligatoire.")
        for key in [
            "sync_interval_seconds",
            "backup_reminder_days",
            "integrity_check_days",
            "archive_after_months",
            "confirmation_reminder_days",
            "delivery_reminder_days",
        ]:
            minimum, maximum = (
                (15, 600) if key == "sync_interval_seconds" else (1, 3650)
            )
            value = parse_decimal(values[key], key, minimum=minimum, maximum=maximum)
            if value != value.to_integral_value():
                raise ValueError("Les délais doivent être des nombres entiers.")
            values[key] = str(int(value))
        changed = any(
            values[k] != self.window.database.get_settings().get(k, "")
            for k in ["user_name", "collaboration_enabled", "shared_workspace_path"]
        )
        if changed and self.window.prepare.cart.lines:
            if not self.window.allow_discard_or_save():
                return False
            self.window.prepare.reset()
        previous = self.window.database.get_settings()
        # Les réglages permettent aussi de désactiver un partage devenu inaccessible.
        if not self.window.operations.guard.acquire(blocking=False):
            raise ValueError(
                "Attendez la fin de la synchronisation avant de changer les réglages."
            )
        try:
            self.window.database.save_settings(values)
            try:
                if changed or (
                    values["collaboration_enabled"] == "1"
                    and self.window.operations.manager is None
                ):
                    self.window.operations.configure()
            except Exception:
                self.window.database.save_settings(
                    {key: previous.get(key, "") for key in values}
                )
                raise
        finally:
            self.window.operations.guard.release()
        self.baseline = self.values()
        self.window.configure_sync_timer()
        self.window.sync_collaboration()
        self.window.notify("Paramètres enregistrés.")
        self.refresh()
        return True

    @action
    def browse_file(self, key):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir une image", "", "Images (*.png *.jpg *.jpeg)"
        )
        if path:
            self.widget(key).setText(portable_path(path))

    def browse_directory(self, key):
        path = QFileDialog.getExistingDirectory(
            self, "Choisir un dossier", self.widget(key).text()
        )
        if path:
            self.widget(key).setText(path)

    def sync(self):
        if self.save():
            self.window.sync_collaboration(force=True)

    @action
    def open_share(self):
        path = Path(self.widget("shared_workspace_path").text())
        if not path.is_dir():
            raise ValueError("Dossier partagé indisponible.")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def test_share(self):
        path = self.widget("shared_workspace_path").text().strip()
        if not path:
            self.status.setText("Choisissez d'abord le dossier partagé.")
            return

        def work(*, cancel, progress):
            return CollaborationManager.test_path(path)

        def done(result, error):
            if error:
                self.window.report_error(error)
                return
            self.status.setText(
                f"Lecture : {result.readable} · Écriture : {result.writable} · Renommage atomique : {result.atomic_rename} · Espace existant : {result.workspace_found}"
            )

        self.window.jobs.submit("test-share", work, done)

    def maintenance(self, key, function, done):
        def work(*, cancel, progress):
            with self.window.operations.guard:
                return function()

        def result(value, error):
            if error:
                self.window.report_error(error)
            else:
                done(value)
                self.window.data_changed()

        self.window.jobs.submit(key, work, result)

    def backup(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Sauvegarde complète",
            str(BACKUP_DIR / f"horizon-{datetime.now():%Y%m%d-%H%M%S}.zip"),
            "Archive ZIP (*.zip)",
        )
        if not path:
            return

        def done(destination):
            self.window.database.save_settings(
                {
                    "last_backup_at": datetime.now().isoformat(timespec="seconds"),
                    "last_backup_path": str(destination),
                }
            )
            self.status.setText("Sauvegarde complète créée : " + str(destination))

        self.maintenance(
            "backup", partial(create_complete_backup, self.window.database, path), done
        )

    def integrity(self):
        def done(result):
            ok, detail = result
            self.window.database.save_settings(
                {
                    "last_integrity_check_at": datetime.now().isoformat(
                        timespec="seconds"
                    ),
                    "last_integrity_check_result": "OK" if ok else detail,
                }
            )
            self.status.setText("Contrôle d'intégrité : " + ("OK" if ok else detail))

        self.maintenance("integrity", self.window.database.quick_integrity_check, done)

    @action
    def archive(self):
        months = int(
            parse_decimal(
                self.widget("archive_after_months").text(),
                "Mois",
                minimum=1,
                maximum=3650,
            )
        )
        before = months_before(date.today(), months)
        if (
            QMessageBox.question(
                self,
                "Archiver",
                f"Archiver les commandes livrées datant d'avant le {before:%d/%m/%Y} ? Elles resteront consultables dans l'historique.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.maintenance(
            "archive",
            partial(self.window.database.archive_old_orders, before),
            lambda ids: self.status.setText(f"{len(ids)} commande(s) archivée(s)."),
        )
