"""Accueil et statistiques construits à partir des commandes réellement envoyées."""

from functools import partial

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QVBoxLayout, QWidget

from .models import RowsModel
from .services import currency, number
from .widgets import Chart, Metric, button, card, label, table


class OverviewPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        header = QHBoxLayout()
        text = QVBoxLayout()
        text.addWidget(label("VOTRE ESPACE DE TRAVAIL", "eyebrow"))
        text.addWidget(label("Vue d'ensemble", "title"))
        text.addWidget(label("Préparer, suivre et vérifier vos commandes.", "muted"))
        header.addLayout(text, 1)
        header.addWidget(button("Préparer une commande", window.new_order, "primary"))
        layout.addLayout(header)
        row = QHBoxLayout()
        self.metrics = [
            Metric(t)
            for t in [
                "À préparer / envoyer",
                "Livraisons à suivre",
                "Engagé ce mois-ci · HT",
                "Articles à vérifier",
            ]
        ]
        for m in self.metrics:
            row.addWidget(m, 1)
        layout.addLayout(row)
        middle = QHBoxLayout()
        graph, body = card()
        body.addWidget(label("Vos achats au fil des mois", "heading"))
        body.addWidget(label("Montants HT des commandes envoyées", "muted"))
        self.chart = Chart()
        body.addWidget(self.chart)
        middle.addWidget(graph, 3)
        tasks, body = card()
        body.addWidget(label("À traiter", "heading"))
        self.check = button(
            "Consulter les articles à vérifier", self.open_review, "accent"
        )
        body.addWidget(self.check)
        body.addWidget(
            button(
                "Reprendre un brouillon",
                lambda: window.open_orders("À préparer / envoyer"),
            )
        )
        body.addWidget(
            button("Suivre les livraisons", lambda: window.open_orders("À recevoir"))
        )
        body.addStretch()
        body.addWidget(
            label(
                "Horizon alpha travaille uniquement dans son profil d'essai. La collaboration n'est pas activée.",
                "muted",
                True,
            )
        )
        middle.addWidget(tasks, 2)
        layout.addLayout(middle)
        recent, body = card()
        body.addWidget(label("Dernières commandes", "heading"))
        self.model = RowsModel(
            [
                ("Commande", lambda r: r["order_number"], False),
                ("Fournisseur", lambda r: r["supplier_name"], False),
                ("État", lambda r: r["status"], False),
                ("Montant HT", lambda r: currency(r["total_ht"]), True),
            ],
            self,
        )
        self.table = table(self.model)
        self.table.setMinimumHeight(200)
        self.table.doubleClicked.connect(
            lambda index: window.open_order(self.model.rows[index.row()]["id"])
        )
        body.addWidget(self.table)
        layout.addWidget(recent, 1)

    def open_review(self):
        self.window.catalog.browser.filter.setCurrentIndex(2)
        self.window.navigate("catalog")

    def refresh(self):
        self.window.jobs.submit("overview", self.window.service.overview, self.result)

    def result(self, data, error):
        if error:
            self.window.report_error(error)
            return
        if not data:
            return
        dash = data["dashboard"]
        current = data["statistics"]["values"][-1]
        details = [
            (data["drafts"], "Commandes non envoyées"),
            (dash["pending_deliveries"], "Commandes envoyées en attente"),
            (currency(current), "Commandes envoyées uniquement"),
            (data["review"], "Contrôles du catalogue"),
        ]
        for metric, (value, caption) in zip(self.metrics, details):
            metric.set_value(value, caption)
        self.chart.set_values(
            data["statistics"]["labels"], data["statistics"]["values"]
        )
        self.check.setText(f"Vérifier {data['review']} article(s)")
        self.model.replace(data["orders"])


class StatisticsPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        layout.addWidget(label("Statistiques", "title"))
        layout.addWidget(
            label(
                "Montants engagés, fournisseurs et délais des commandes envoyées.",
                "muted",
            )
        )
        filters = QHBoxLayout()
        self.period = QComboBox()
        self.period.setAccessibleName("Période des statistiques")
        for text, n in [
            ("6 derniers mois", 6),
            ("3 derniers mois", 3),
            ("12 derniers mois", 12),
        ]:
            self.period.addItem(text, n)
        self.supplier = QComboBox()
        self.supplier.setAccessibleName("Fournisseur des statistiques")
        self.supplier.addItem("Tous les fournisseurs", None)
        self.period.currentIndexChanged.connect(self.refresh)
        self.supplier.currentIndexChanged.connect(self.refresh)
        filters.addWidget(self.period)
        filters.addWidget(self.supplier)
        filters.addStretch()
        layout.addLayout(filters)
        self.metrics = [
            Metric(t)
            for t in ("Montant engagé HT", "Commandes envoyées", "Fournisseurs")
        ]
        row = QHBoxLayout()
        for m in self.metrics:
            row.addWidget(m)
        layout.addLayout(row)
        graphs = QHBoxLayout()
        box, body = card()
        body.addWidget(label("Évolution des achats", "heading"))
        self.line = Chart()
        body.addWidget(self.line)
        graphs.addWidget(box, 3)
        box, body = card()
        body.addWidget(label("Répartition par fournisseur", "heading"))
        body.addWidget(label("Sélectionnez une barre pour filtrer", "muted"))
        self.bars = Chart("bars")
        self.bars.selected.connect(self.select_supplier)
        body.addWidget(self.bars)
        graphs.addWidget(box, 2)
        layout.addLayout(graphs)
        box, body = card()
        body.addWidget(label("Détail par fournisseur", "heading"))
        self.model = RowsModel(
            [
                ("Fournisseur", lambda r: r["name"], False),
                ("Commandes", lambda r: r["orders"], True),
                ("Montant HT", lambda r: currency(r["total_ht"]), True),
                (
                    "Délai réception",
                    lambda r: (
                        number(r["delivery_days"], 1) + " j"
                        if r["delivery_days"] is not None
                        else "—"
                    ),
                    True,
                ),
            ],
            self,
        )
        body.addWidget(table(self.model))
        layout.addWidget(box, 1)

    def select_supplier(self, sid):
        index = self.supplier.findData(sid)
        if index >= 0:
            self.supplier.setCurrentIndex(index)

    def reload_suppliers(self):
        current = self.supplier.currentData()
        self.supplier.blockSignals(True)
        self.supplier.clear()
        self.supplier.addItem("Tous les fournisseurs", None)
        for row in self.window.database.list_suppliers():
            self.supplier.addItem(row["name"], row["id"])
        self.supplier.setCurrentIndex(max(0, self.supplier.findData(current)))
        self.supplier.blockSignals(False)

    def refresh(self, *_):
        self.window.jobs.submit(
            "statistics",
            partial(
                self.window.service.statistics,
                self.period.currentData(),
                self.supplier.currentData(),
            ),
            self.result,
        )

    def result(self, data, error):
        if error:
            self.window.report_error(error)
            return
        if not data:
            return
        totals = data["totals"]
        for metric, value, caption in zip(
            self.metrics,
            [currency(totals["total_ht"]), totals["orders"], totals["suppliers"]],
            [
                "Brouillons exclus",
                "Sur la période sélectionnée",
                "Avec commande envoyée",
            ],
        ):
            metric.set_value(value, caption)
        self.line.set_values(data["labels"], data["values"])
        rows = data["suppliers"]
        self.bars.set_values(
            [r["name"] for r in rows[:6]],
            [r["total_ht"] for r in rows[:6]],
            [r["id"] for r in rows[:6]],
        )
        self.model.replace(rows)
