"""Historique d'import, catalogue partagé et évolutions des articles commandés."""

from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from .dates import format_month
from .forms import action, selected_row
from .models import RowsModel, date_column
from .services import number, unit_currency
from .widgets import button, label, table


class ImportsPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.pending = None
        self.publication = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label("Mise à jour CAHPP", "title"))
        layout.addWidget(
            label(
                "Catalogues complets et évolutions mensuelles : aperçu, contrôle de chronologie, sauvegarde et application transactionnelle.",
                "muted",
                True,
            )
        )
        row = QHBoxLayout()
        row.addWidget(
            button("Importer un fichier Excel…", window.choose_catalog, "primary")
        )
        self.shared = button("Installer le catalogue partagé", self.install_shared)
        row.addWidget(self.shared)
        self.publish = button("Publier le catalogue local", self.publish_local)
        self.publish.setEnabled(False)
        row.addWidget(self.publish)
        row.addWidget(button("Actualiser", self.refresh))
        layout.addLayout(row)
        self.status = label("", "muted", True)
        layout.addWidget(self.status)
        self.model = RowsModel(
            [
                ("Fichier", lambda r: r["filename"], False),
                date_column("Date d'import", "imported_at", include_time=True),
                ("Lignes", lambda r: r["row_count"], True),
                ("Ajouts", lambda r: r["added_count"], True),
                ("Modifications", lambda r: r["updated_count"], True),
            ]
        )
        self.table = table(self.model)
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        row.addWidget(button("Changements des articles commandés", self.changes))
        row.addWidget(button("Changements des favoris", lambda: self.changes(True)))
        row.addStretch()
        layout.addLayout(row)

    def refresh(self):
        manager = self.window.operations.manager

        def work(*, cancel, progress):
            return (
                [dict(r) for r in self.window.database.latest_imports()],
                manager.pending_catalog() if manager else None,
                manager.catalog_publication_status() if manager else {},
            )

        def done(result, error):
            if error:
                self.window.report_error(error)
                return
            rows, self.pending, self.publication = result
            self.model.replace(rows)
            if rows:
                self.table.selectRow(0)
            self.shared.setEnabled(bool(self.pending))
            self.publish.setEnabled(bool(self.publication.get("can_publish")))
            if self.pending:
                token = str(
                    self.pending.get("sha256") or self.pending.get("version") or ""
                )
                if token and token != self.window.catalog_prompted:
                    self.window.catalog_prompted = token
                    self.window.notify(
                        "Un nouveau catalogue partagé est disponible dans Mise à jour CAHPP."
                    )
            if self.publication.get("local_unpublished"):
                message = "Le dernier import local n’a pas été publié sur le partage : " + str(self.publication.get("local_source", ""))
                message += (". Cliquez sur « Publier le catalogue local »." if self.publication.get("can_publish")
                            else ". Le partage a une autre version ; résolvez cet écart avant de publier.")
            elif self.pending:
                message = "Un catalogue partagé est disponible à installer."
            elif manager:
                message = "Le dernier import local est publié sur le partage." if self.publication.get("published") else "Aucun nouveau catalogue partagé à installer."
            else:
                message = "Le dossier partagé n’est pas activé sur ce profil."
            if manager:
                local = format_month(self.publication.get("local_period")) or "période non précisée"
                shared = format_month(self.publication.get("shared_period")) or "période non précisée"
                message += f"\nPériode locale : {local} · Période partagée : {shared}."
            self.status.setText(message)

        self.window.jobs.submit("imports-list", work, done)

    @action
    def install_shared(self):
        if self.pending and self.window.operations.manager:
            path = self.window.operations.manager.catalog_source(self.pending)
            self.window.start_catalog(path, shared_manifest=self.pending)

    @action
    def publish_local(self):
        window = self.window
        if window.import_busy or window.sync_running:
            raise ValueError("Attendez la fin de l’opération en cours.")
        source = None
        if not self.publication.get("durable_source"):
            source, _ = QFileDialog.getOpenFileName(
                self, "Retrouver le fichier du dernier import local", str(self.publication.get("local_source", "")),
                "Classeurs Excel (*.xlsx)",
            )
            if not source:
                return
        window.import_busy = True
        window.progress.setRange(0, 100)
        window.progress.show()

        def work(*, cancel, progress):
            return window.operations.publish_latest_catalog(source, cancel=cancel, progress=progress)

        def done(result, error):
            window.end_import()
            window.data_changed()
            if error:
                window.report_error(error)
            else:
                QMessageBox.information(window, "Catalogue publié",
                    "Le catalogue local a été publié sur le partage, sans réimporter les tarifs. "
                    "Les autres postes peuvent l’installer depuis Mise à jour CAHPP.")

        window.jobs.submit("catalog-publication", work, done)

    @action
    def changes(self, favorite=False):
        row = selected_row(self.table, self.model)
        if not row:
            raise ValueError("Sélectionnez un import.")
        dialog = QDialog(self.window)
        dialog.setWindowTitle(
            "Évolutions des favoris"
            if favorite
            else "Évolutions des articles commandés"
        )
        dialog.resize(1100, 650)
        body = QVBoxLayout(dialog)
        model = RowsModel(
            [
                (
                    "Article / fournisseur",
                    lambda r: r["designation"] + "\n" + r["supplier_name"],
                    False,
                ),
                ("Ancien PU HT", lambda r: unit_currency(r["old_price"]), True),
                ("Nouveau PU HT", lambda r: unit_currency(r["new_price"]), True),
                ("Ancien conditionnement", lambda r: number(r["old_pack"]), True),
                ("Nouveau conditionnement", lambda r: number(r["new_pack"]), True),
            ]
        )
        values = (
            self.window.database.favorite_changes_for_import(row["id"])
            if favorite
            else self.window.database.ordered_changes_for_import(row["id"])
        )
        model.replace([dict(r) for r in values])
        body.addWidget(label(f"{len(model.rows)} changement(s)", "heading"))
        body.addWidget(table(model), 1)
        body.addWidget(button("Fermer", dialog.accept))
        dialog.exec()
