"""Réglages métier, collaboration et diagnostic Qt complet."""

import os
import time
from datetime import date, datetime
from functools import partial
from pathlib import Path

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import QTimer, QUrl, qVersion
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QLineEdit,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QPlainTextEdit,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..collaboration import CollaborationManager
from ..file_lock import FileLockBusy, exclusive_file
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
from .mobile_sync import Relay, synchronize
from .mobile_space import WorkspaceBindingRequired
from .credentials import Credentials
from .mobile_devices import MobileDevicesDialog


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
                + f"\n\nHORIZON\n-------\nProfil : {self.window.profile}\nMode : {self.window.info.get('mode', '')}\nTâches au déclenchement : {self.task_count}\nImport en cours : {self.import_running}\nRéceptions Android : {self.mobile_result}\nCoffre PC : {self.credential_info['backend']} · mémorisation : {self.credential_info['remembered']}\nCapacité relais : {self.relay_capacity_info}\n"
            )

    def busy(self, value, message=""):
        self.status.setText(message)
        self.refresh_button.setEnabled(not value)
        self.repair_button.setEnabled(not value)
        self.copy_button.setEnabled(bool(self.report))
        self.export_button.setEnabled(bool(self.report))

    def run(self):
        self.relay_metrics = dict(getattr(self.window.operations, "last_mobile_maintenance", {}))
        m = self.relay_metrics
        self.relay_capacity_info = (
            f"{m['pending_items']} demande(s), {m['pending_bytes']} octets en attente ; "
            f"{m['documents']} document(s), {m['document_bytes']} octets, {m['orphan_documents']} orphelin(s)."
            if 'pending_items' in m else "Non contrôlée pendant cette session."
        )
        self.credential_info = self.window.preferences.credentials.diagnostic()
        self.mobile_result = self.window.preferences.mobile_status.text() or "Aucun échange pendant cette session."
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
                    ("Mettre à niveau le partage…", self.upgrade_share),
                ]:
                    row.addWidget(button(text, callback))
                body.addLayout(row)
                row = QHBoxLayout()
                row.addWidget(button("Test à deux postes : réserver (30 s)", partial(self.check_share_lock, True)))
                row.addWidget(button("Test à deux postes : vérifier", partial(self.check_share_lock, False)))
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
                    label("Restauration et import", "heading")
                )
                body.addWidget(
                    label(
                        "Pour restaurer une sauvegarde Horizon, extrayez tout le ZIP puis choisissez le fichier data/commandes_cahpp.sqlite3. Vous pouvez aussi sélectionner une base CAHPP 1.6. Les données seront copiées dans un nouveau profil.",
                        "muted",
                        True,
                    )
                )
                self.copy_database_button = button(
                    "Restaurer une sauvegarde ou importer une base CAHPP…", window.choose_database
                )
                body.addWidget(self.copy_database_button)
            body.addStretch()
            self.tabs.addTab(page, title)
            if title == "Établissement":
                self.tabs.addTab(window.suppliers, "Fournisseurs")
        mobile = self.mobile_page = QWidget()
        body = QVBoxLayout(mobile)
        body.addWidget(label(
            "Configurez le relais puis synchronisez pour rendre les commandes envoyées "
            "disponibles sur le téléphone. Activez d’abord le dossier partagé dans Collaboration.",
            "muted", True,
        ))
        self.mobile_fields = Fields(body)
        self.mobile_url = self.mobile_fields.add("Adresse HTTPS du relais", "url")
        self.mobile_url.setPlaceholderText("https://horizon.macq.xyz")
        self.mobile_token = self.mobile_fields.add("Clé PC du relais", "token")
        self.mobile_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.mobile_token.setPlaceholderText("Valeur de HORIZON_PC_TOKEN dans Portainer")
        self.mobile_url.setText(window.settings.value(
            "mobile/url", os.environ.get("HORIZON_RELAY_URL", ""), type=str,
        ))
        self.credentials = Credentials(window.profile, window.settings)
        self.mobile_token.setText(self.credentials.load(fallback=os.environ.get("HORIZON_PC_TOKEN", "")))
        self.mobile_remember = QCheckBox("Mémoriser la clé dans le coffre sécurisé du système")
        self.mobile_remember.setChecked(self.credentials.remembered)
        body.addWidget(self.mobile_remember)
        self.mobile_proxy = QCheckBox("Utiliser le proxy système pour joindre le relais")
        self.mobile_proxy.setChecked(window.settings.value("mobile/use_system_proxy", False, type=bool))
        body.addWidget(self.mobile_proxy)
        self.mobile_auto = QCheckBox("Synchroniser automatiquement avec Android")
        self.mobile_auto.setChecked(window.settings.value("mobile/automatic", True, type=bool))
        body.addWidget(self.mobile_auto)
        self.mobile_interval = QSpinBox()
        self.mobile_interval.setRange(15, 3600)
        self.mobile_interval.setSuffix(" s")
        self.mobile_interval.setValue(window.settings.value("mobile/interval", 60, type=int))
        self.mobile_fields.form.addRow("Intervalle de synchronisation", self.mobile_interval)
        row = QHBoxLayout()
        row.addWidget(button("Enregistrer la connexion", self.save_mobile))
        self.mobile_button = button("Synchroniser avec Android", self.sync_mobile)
        row.addWidget(self.mobile_button)
        body.addLayout(row)
        body.addWidget(button("Rattacher le relais à cette base…", self.bind_mobile_workspace))
        body.addWidget(button("Gérer les téléphones autorisés…", self.manage_mobile_devices))
        self.mobile_status = label(self.credentials.warning, "muted", True)
        body.addWidget(self.mobile_status)
        body.addStretch()
        self.tabs.addTab(mobile, "Android")
        self.mobile_config = (
            self.mobile_url.text().strip(), self.mobile_token.text().strip(),
            self.mobile_proxy.isChecked(),
        )
        self.mobile_timer = QTimer(self)
        self.mobile_timer.timeout.connect(lambda: self.sync_mobile(automatic=True))
        self.configure_mobile_timer()
        QTimer.singleShot(1500, lambda: self.sync_mobile(automatic=True))
        self.about = AboutPage(window)
        self.tabs.addTab(self.about, "À propos")
        row = QHBoxLayout()
        self.save_button = button("Enregistrer les paramètres", self.save, "primary")
        row.addWidget(self.save_button)
        row.addWidget(button("Diagnostics et débogage", window.open_diagnostics))
        row.addStretch()
        layout.addLayout(row)
        self.status = label("", "muted", True)
        self.window.jobs.progress.connect(self.share_lock_progress)
        layout.addWidget(self.status)
        self.tabs.currentChanged.connect(self.tab_changed)

    def tab_changed(self):
        suppliers_selected = self.tabs.currentWidget() is self.window.suppliers
        self.save_button.setVisible(
            not suppliers_selected
            and self.tabs.currentWidget() not in (self.about, self.mobile_page)
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

    @action
    def save_mobile(self):
        url = self.mobile_url.text().strip()
        token = self.mobile_token.text().strip()
        Relay(url, token, use_system_proxy=self.mobile_proxy.isChecked())
        self.window.settings.setValue("mobile/use_system_proxy", self.mobile_proxy.isChecked())
        self.window.settings.setValue("mobile/url", url)
        self.credentials.store(token, url, remember=self.mobile_remember.isChecked())
        self.mobile_remember.setChecked(self.credentials.remembered)
        self.window.settings.setValue("mobile/automatic", self.mobile_auto.isChecked())
        self.window.settings.setValue("mobile/interval", self.mobile_interval.value())
        self.window.settings.sync()
        self.mobile_config = (url, token, self.mobile_proxy.isChecked())
        self.configure_mobile_timer()
        self.mobile_status.setText(self.credentials.warning or "Connexion enregistrée. Vous pouvez synchroniser avec Android.")
        return url, token

    @action
    def manage_mobile_devices(self):
        if not self.window.operations.manager:
            raise ValueError("Connectez d’abord le partage de cette base.")
        if self.save_mobile():
            dialog = MobileDevicesDialog(self.window, self.mobile_config)
            dialog.exec()

    def configure_mobile_timer(self):
        self.mobile_next_due = 0
        if self.window.settings.value("mobile/automatic", True, type=bool):
            self.mobile_timer.start(self.window.settings.value("mobile/interval", 60, type=int) * 1000)
        else:
            self.mobile_timer.stop()

    @action
    def bind_mobile_workspace(self):
        if not self.window.operations.manager:
            raise ValueError("Connectez d’abord le dossier partagé de cette base.")
        if not self.save_mobile():
            return
        url, token, proxy = self.mobile_config
        expected = self.window.operations.manager.workspace_id
        relay = Relay(url, token, use_system_proxy=proxy)

        def work(*, cancel, progress):
            try:
                relay.connect_workspace(expected)
            except WorkspaceBindingRequired as exc:
                return exc.counts
            return None

        def done(counts, error):
            if error:
                self.window.report_error(error)
                return
            if counts is None:
                self.mobile_status.setText("Le relais est rattaché à cette base.")
                return
            answer = QMessageBox.question(
                self, "Rattacher les données existantes",
                f"Le relais contient {counts.get('orders', 0)} référence(s) de commandes, "
                f"{counts.get('receipts', 0)} réception(s) et {counts.get('mobile_actions', 0)} demande(s).\n\n"
                "Confirmez que ces données proviennent bien de cette base. Après rattachement, "
                "tous les postes et téléphones devront utiliser les nouvelles versions compatibles. "
                "Les téléphones conserveront séparément leurs anciennes données locales.\n\n"
                "Rattacher ce relais à cette base ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

            def bind(*, cancel, progress):
                relay.connect_workspace(expected, adopt_existing=True)

            def bound(result, error):
                if error:
                    self.window.report_error(error)
                else:
                    self.mobile_status.setText("Relais rattaché. Reconnectez les téléphones dans leurs réglages.")

            self.window.jobs.submit("mobile-binding", bind, bound)

        self.window.jobs.submit("mobile-binding", work, done)

    @action
    def sync_mobile(self, automatic=False):
        window = self.window
        if window.closing or any(key == "mobile-sync" for key, _ in window.jobs.tasks):
            return
        if automatic:
            if not self.mobile_timer.isActive() or time.monotonic() < self.mobile_next_due:
                return
            if (window.import_busy or window.sync_running or window.dirty_forms()
                    or window.operations.editing_order is not None or window.jobs.busy):
                return
            url, token, use_system_proxy = self.mobile_config
            if not url or not token or not window.operations.manager:
                return
        else:
            connection = self.save_mobile()
            if not connection:
                return
            url, token, use_system_proxy = self.mobile_config
        self.mobile_next_due = time.monotonic() + self.mobile_interval.value()
        self.mobile_connection_info = (
            f"{url} · " + ("proxy système" if use_system_proxy else "connexion directe")
        )
        self.mobile_button.setEnabled(False)
        self.mobile_status.setText("Synchronisation avec le relais en cours…")
        operations = window.operations

        def work(*, cancel, progress):
            if cancel.is_set():
                return None
            return synchronize(operations, Relay(url, token, use_system_proxy=use_system_proxy))

        def finished(result, error):
            self.mobile_button.setEnabled(True)
            stamp = datetime.now().strftime("%H:%M:%S")
            self.mobile_status.setText(
                self.mobile_connection_info + "\n" + stamp + " · "
                + (str(error) if error else (result or "Synchronisation annulée."))
            )
            if error:
                if not automatic:
                    window.report_error(error)
            else:
                window.data_changed()

        window.jobs.submit("mobile-sync", work, finished)

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

    def share_lock_progress(self, key, percent, text):
        if key == "shared-lock-check":
            self.status.setText(text)

    def check_share_lock(self, hold):
        path = self.widget("shared_workspace_path").text().strip()
        if not path or not Path(path).is_dir():
            self.status.setText("Choisissez d'abord un dossier partagé existant.")
            return
        sentinel = Path(path) / "verrous" / ".verification.guard"

        def work(*, cancel, progress):
            try:
                with exclusive_file(sentinel):
                    if not hold:
                        return "Aucune réservation détectée. Démarrez d’abord le test de 30 secondes sur l’autre poste ; si celui-ci est déjà prêt, le partage ne respecte pas l’exclusion."
                    for remaining in range(30, 0, -1):
                        progress(30 - remaining, 30, f"Verrou de test détenu : {remaining} s. Cliquez sur « vérifier » sur l’autre poste.")
                        if cancel.wait(1):
                            return "Test arrêté."
                    return "Réservation de test libérée. Vérifiez maintenant que l’autre poste peut réserver."
            except FileLockBusy:
                return "Exclusion observée : le verrou de test est détenu par l’autre poste. Refaites le test en inversant les postes."

        def done(result, error):
            self.status.setText(str(error) if error else result)

        self.window.jobs.submit("shared-lock-check", work, done)

    @action
    def upgrade_share(self):
        path = self.widget("shared_workspace_path").text().strip()
        if not path:
            raise ValueError("Choisissez d'abord le dossier partagé.")
        if self.window.prepare.cart.lines or self.window.operations.editing_order:
            raise ValueError("Enregistrez puis fermez la commande en préparation avant cette opération.")
        answer = QMessageBox.question(
            self, "Mettre à niveau le partage",
            "Fermez Horizon sur tous les autres postes avant de continuer. "
            "La mise à niveau exige ensuite cette nouvelle version sur tous les postes. "
            "L’identité du partage, les commandes et le catalogue sont conservés.\n\n"
            "Confirmez-vous que les autres applications Horizon sont fermées ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        def work(*, cancel, progress):
            with self.window.operations.guard:
                CollaborationManager.upgrade_workspace(path)

        def done(result, error):
            if error:
                self.window.report_error(error)
                return
            self.status.setText("Partage mis à niveau. Enregistrez les paramètres pour le connecter.")

        self.window.jobs.submit("upgrade-share", work, done)

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
