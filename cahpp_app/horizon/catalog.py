"""Catalogue paginé et recherche différée, commun à la consultation et au panier."""

from functools import partial

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from .dialogs import ProductDialog
from .models import ProductsModel
from .services import currency, number
from .widgets import button, card, label, table
from .forms import action, FormDialog
from ..numbers import parse_decimal


class CatalogBrowser(QWidget):
    selected = Signal(object)
    add_requested = Signal(object)

    def __init__(self, window, key, *, supplier_picker=True):
        super().__init__()
        self.window = window
        self.key = key
        self.supplier_id = None
        self.limit = 100
        self.setMinimumWidth(0)
        self.model = ProductsModel(self)
        self.rows = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        controls = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("Rechercher un article, une référence…")
        self.query.setClearButtonEnabled(True)
        self.query.setAccessibleName("Recherche catalogue")
        self.query.textChanged.connect(self.schedule)
        controls.addWidget(self.query, 1)
        self.filter = QComboBox()
        self.filter.addItems(
            ["Articles actifs", "Favoris", "À vérifier", "Actifs et inactifs"]
        )
        self.filter.setMaximumWidth(180)
        self.filter.setAccessibleName("Filtre du catalogue")
        self.filter.currentIndexChanged.connect(self.schedule)
        controls.addWidget(self.filter)
        layout.addLayout(controls)
        self.suppliers = QComboBox()
        self.suppliers.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.suppliers.setMinimumContentsLength(12)
        self.suppliers.setAccessibleName("Fournisseur du catalogue")
        if supplier_picker:
            self.reload_suppliers()
            layout.addWidget(self.suppliers)
            self.suppliers.currentIndexChanged.connect(self.schedule)
        self.has_supplier_picker = supplier_picker
        box, body = card()
        body.setContentsMargins(0, 0, 0, 0)
        self.table = table(self.model)
        self.table.doubleClicked.connect(self._double_click)
        self.table.selectionModel().selectionChanged.connect(self._selection)
        body.addWidget(self.table)
        layout.addWidget(box, 1)
        footer = QHBoxLayout()
        self.status = label(
            "Recherches limitées aux premières références.", "muted", True
        )
        footer.addWidget(self.status, 1)
        self.more = button("Afficher 100 de plus", self.load_more)
        self.more.hide()
        footer.addWidget(self.more)
        layout.addLayout(footer)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(280)
        self.timer.timeout.connect(self.search)

    def reload_suppliers(self):
        current = self.suppliers.currentData()
        self.suppliers.blockSignals(True)
        self.suppliers.clear()
        self.suppliers.addItem("Tous les fournisseurs", None)
        for row in self.window.database.list_suppliers(used_only=True):
            self.suppliers.addItem(row["name"], row["id"])
        index = self.suppliers.findData(current)
        self.suppliers.setCurrentIndex(max(0, index))
        self.suppliers.blockSignals(False)

    def schedule(self, *_):
        self.window.jobs.cancel(self.key)
        self.limit = 100
        self.status.setText("Recherche en cours…")
        self.timer.start()

    def search(self):
        self.timer.stop()
        supplier = (
            self.suppliers.currentData()
            if self.has_supplier_picker
            else self.supplier_id
        )
        self.window.jobs.submit(
            self.key,
            partial(
                self.window.service.search,
                query=self.query.text(),
                supplier_id=supplier,
                favorite=self.filter.currentIndex() == 1,
                review=self.filter.currentIndex() == 2,
                include_inactive=self.filter.currentIndex() == 3,
                limit=self.limit + 1,
            ),
            self._result,
        )

    def _result(self, result, error):
        if error:
            self.status.setText("Recherche impossible : " + str(error))
            self.more.hide()
            return
        if result is None:
            return
        previous = self.selected_product()
        self.rows = result.rows[: self.limit]
        self.model.replace(self.rows)
        self.more.setVisible(len(result.rows) > self.limit and self.limit < 1000)
        suffix = (
            " · affinez la recherche pour voir d'autres articles"
            if self.limit >= 1000 and len(result.rows) > self.limit
            else ""
        )
        self.status.setText(
            f"{len(self.rows)} article(s) affiché(s) · {result.elapsed_ms} ms"
            + suffix
            + (" · " + result.warning if result.warning else "")
        )
        index = next(
            (
                i
                for i, r in enumerate(self.model.rows)
                if previous and r["id"] == previous["id"]
            ),
            0,
        )
        if self.rows:
            self.table.selectRow(index)
        else:
            self.selected.emit(None)

    def load_more(self):
        self.limit = min(1000, self.limit + 100)
        self.search()

    def selected_product(self):
        indexes = self.table.selectionModel().selectedRows()
        return (
            self.model.rows[indexes[0].row()]
            if indexes and indexes[0].row() < len(self.model.rows)
            else None
        )

    def _selection(self, *_):
        self.selected.emit(self.selected_product())

    def _double_click(self, index):
        if index.isValid():
            self.add_requested.emit(self.model.rows[index.row()])


class CatalogPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.current = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(label("Catalogue", "title"))
        titles.addWidget(
            label("Articles, favoris et informations à vérifier.", "muted")
        )
        header.addLayout(titles, 1)
        header.addWidget(button("Importer CAHPP", window.choose_catalog))
        header.addWidget(
            button("Préparer", lambda: window.navigate("prepare"), "primary")
        )
        layout.addLayout(header)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.browser = CatalogBrowser(window, "catalog")
        self.browser.selected.connect(self.select_product)
        self.browser.add_requested.connect(window.add_product)
        split.addWidget(self.browser)
        detail, body = card()
        detail.setMinimumWidth(225)
        self.badge = label("Sélectionnez un article", "badge")
        self.name = label("Fiche de l'article", "heading", True)
        self.supplier = label("", "muted", True)
        self.facts = label("", "", True)
        self.warning = label("", "warning", True)
        self.warning.hide()
        body.addWidget(self.badge)
        body.addWidget(self.name)
        body.addWidget(self.supplier)
        body.addSpacing(8)
        body.addWidget(self.facts)
        body.addWidget(self.warning)
        self.edit = button("Vérifier / modifier", self.edit_product)
        self.edit.setEnabled(False)
        self.favorite = button("Ajouter aux favoris", self.toggle_favorite)
        self.favorite.setEnabled(False)
        self.add = button("Ajouter au panier", self.add_product, "primary")
        self.add.setEnabled(False)
        body.addWidget(self.edit)
        body.addWidget(self.favorite)
        body.addWidget(self.add)
        self.more_actions = QComboBox()
        self.more_actions.addItems(
            [
                "Quantité habituelle / nom court…",
                "Rétablir les valeurs CAHPP",
                "Archiver un article hors catalogue",
            ]
        )
        body.addWidget(self.more_actions)
        body.addWidget(button("Exécuter l'action", self.additional_action))
        body.addStretch()
        body.addWidget(
            label(
                "Les anciennes commandes conservent leurs valeurs d'origine.",
                "muted",
                True,
            )
        )
        split.addWidget(detail)
        split.setSizes([750, 270])
        split.setStretchFactor(0, 1)
        layout.addWidget(split, 1)

    def refresh(self):
        self.browser.reload_suppliers()
        self.browser.search()

    def select_product(self, p):
        self.current = self.window.database.get_product(p["id"]) if p else None
        p = self.current
        self.edit.setEnabled(bool(p))
        self.favorite.setEnabled(bool(p))
        self.add.setEnabled(
            bool(p) and not p["catalog_review_required"] and bool(p["active"])
        )
        if not p:
            self.name.setText("Sélectionnez un article")
            self.facts.clear()
            self.warning.hide()
            return
        self.name.setText(p["designation"])
        self.supplier.setText(p["supplier_name"] + "\n" + p["supplier_ref"])
        self.badge.setText(
            "Inactif"
            if not p["active"]
            else "À vérifier"
            if p["catalog_review_required"]
            else "Article actif"
        )
        self.facts.setText(
            f"Prix unitaire HT : {currency(p['unit_price'], 4)}\n\nUnités/carton : {number(p['conditionnement'] or p['qml'])}\n\nTVA : {number(p['vat'], 2)} %\n\nCode CAHPP : {p['code_cahpp']}"
        )
        self.warning.setText(p["catalog_review_reason"])
        self.warning.setVisible(p["catalog_review_required"])
        self.favorite.setText(
            "Retirer des favoris" if p["favorite"] else "Ajouter aux favoris"
        )

    @action
    def edit_product(self):
        if self.window.import_busy:
            self.window.notify(
                "Attendez la fin de l’import avant de modifier un article."
            )
            return
        if self.current:
            with self.window.operations.locked_product(self.current["id"]):
                dialog = ProductDialog(self.window.database, self.current["id"], self)
                if dialog.exec():
                    self.window.data_changed()

    @action
    def toggle_favorite(self):
        if self.current:
            with self.window.operations.locked_product(self.current["id"]):
                self.window.database.set_favorite(
                    self.current["id"], not self.current["favorite"]
                )
            self.window.data_changed()

    @action
    def additional_action(self):
        if not self.current:
            raise ValueError("Sélectionnez un article.")
        if self.more_actions.currentIndex() == 0:
            self.edit_favorite()
        elif self.more_actions.currentIndex() == 1:
            if self.current["source"] == "LOCAL":
                raise ValueError("Cet article ne provient pas du catalogue CAHPP.")
            if (
                QMessageBox.question(
                    self,
                    "Rétablir le catalogue",
                    "Supprimer les corrections et reprendre les valeurs CAHPP ?",
                )
                == QMessageBox.StandardButton.Yes
            ):
                with self.window.operations.locked_product(self.current["id"]):
                    self.window.database.reset_product_override(self.current["id"])
                self.window.data_changed()
        else:
            if self.current["source"] != "LOCAL":
                raise ValueError(
                    "Seuls les articles hors catalogue peuvent être archivés manuellement."
                )
            if (
                QMessageBox.question(
                    self,
                    "Archiver l'article",
                    "Archiver cet article hors catalogue ? Les anciennes commandes sont conservées.",
                )
                == QMessageBox.StandardButton.Yes
            ):
                with self.window.operations.locked_product(self.current["id"]):
                    self.window.database.archive_manual_product(self.current["id"])
                self.window.data_changed()

    def edit_favorite(self):
        pid = self.current["id"]
        dialog = FormDialog(self.window, "Favori et quantité habituelle")
        dialog.fields.add("Nom court", "short_name").setText(self.current["short_name"])
        dialog.fields.add("Cartons habituels", "usual_cartons").setText(
            number(self.current["usual_cartons"], 3)
        )

        @action
        def save(d):
            values = d.fields.values()
            quantity = parse_decimal(
                values["usual_cartons"], "Cartons habituels", minimum=0
            )
            if quantity <= 0:
                raise ValueError("La quantité habituelle doit être supérieure à zéro.")
            with self.window.operations.locked_product(pid):
                self.window.database.set_favorite(
                    pid, True, float(quantity), values["short_name"]
                )
            d.accept()
            self.window.data_changed()

        dialog.actions(lambda: save(dialog))
        dialog.exec()

    def add_product(self):
        if self.current:
            self.window.add_product(self.current)
