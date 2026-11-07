"""Historique d'import, catalogue partagé et évolutions des articles commandés."""

from PySide6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QWidget

from .forms import action, selected_row
from .models import RowsModel
from .services import currency, number
from .widgets import button, label, table


class ImportsPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.pending = None
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
        row.addWidget(button("Actualiser", self.refresh))
        layout.addLayout(row)
        self.status = label("", "muted", True)
        layout.addWidget(self.status)
        self.model = RowsModel(
            [
                ("Fichier", lambda r: r["filename"], False),
                ("Date d'import", lambda r: r["imported_at"], False),
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
            )

        def done(result, error):
            if error:
                self.window.report_error(error)
                return
            rows, self.pending = result
            self.model.replace(rows)
            if rows:
                self.table.selectRow(0)
            self.shared.setEnabled(bool(self.pending))
            self.status.setText(
                "Catalogue partagé disponible : " + str(self.pending.get("version", ""))
                if self.pending
                else "Aucun nouveau catalogue partagé à installer."
            )

        self.window.jobs.submit("imports-list", work, done)

    @action
    def install_shared(self):
        if self.pending and self.window.operations.manager:
            path = self.window.operations.manager.catalog_source(self.pending)
            self.window.start_catalog(path, shared_manifest=self.pending)

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
                ("Ancien PU HT", lambda r: currency(r["old_price"], 4), True),
                ("Nouveau PU HT", lambda r: currency(r["new_price"], 4), True),
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
