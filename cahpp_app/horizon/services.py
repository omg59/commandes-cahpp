"""Cas d'usage partagés par les écrans Qt, sans dépendance à un widget."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from ..database import CATALOG_REVIEW_SQL, Database, money
from ..numbers import parse_decimal


def number(value, digits=0):
    if value is None:
        return "—"
    result = f"{Decimal(str(value)):,.{digits}f}"
    return result.replace(",", " ").replace(".", ",")


def currency(value, digits=2):
    return "Prix absent" if value is None else number(value, digits) + " €"


@dataclass
class CartLine:
    product_id: int
    code_cahpp: str
    supplier_ref: str
    designation: str
    cartons: Decimal
    units_per_carton: Decimal
    unit_price: Decimal
    vat: Decimal

    @property
    def total_ht(self):
        return (self.cartons * self.units_per_carton * self.unit_price).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )

    def as_mapping(self):
        return dict(vars(self))


class Cart:
    def __init__(self):
        self.supplier_id = None
        self.lines: list[CartLine] = []
        self.order_id = None
        self.dirty = False

    def add(self, product, *, price=None, quantity=1, packaging=None):
        if not product["active"] or product["catalog_review_required"]:
            raise ValueError(
                "Vérifiez d'abord les informations de l'article dans le catalogue."
            )
        if self.lines and product["supplier_id"] != self.supplier_id:
            raise ValueError(
                "Une commande ne peut contenir qu'un fournisseur. Enregistrez le brouillon avant de changer de fournisseur."
            )
        pack = parse_decimal(
            packaging
            if packaging is not None
            else product["conditionnement"] or product["qml"],
            "Unités par carton",
            minimum=0,
        )
        unit_price = parse_decimal(
            product["unit_price"] if price is None else price,
            "Prix unitaire",
            minimum=0,
        )
        vat = parse_decimal(product["vat"], "TVA", minimum=0, maximum=100)
        qty = parse_decimal(quantity, "Cartons", minimum=0)
        if pack <= 0 or qty <= 0:
            raise ValueError("Les quantités doivent être supérieures à zéro.")
        existing = next(
            (line for line in self.lines if line.product_id == product["id"]), None
        )
        if existing:
            existing.cartons += qty
        else:
            self.lines.append(
                CartLine(
                    product["id"],
                    product["code_cahpp"],
                    product["supplier_ref"],
                    product["designation"],
                    qty,
                    pack,
                    unit_price,
                    vat,
                )
            )
        self.supplier_id = product["supplier_id"]
        self.dirty = True

    def set_quantity(self, index, value):
        quantity = parse_decimal(value, "Cartons", minimum=0)
        if quantity <= 0:
            raise ValueError("La quantité doit être supérieure à zéro.")
        self.lines[index].cartons = quantity
        self.dirty = True

    def remove(self, index):
        del self.lines[index]
        self.dirty = True

    @property
    def total_ht(self):
        return sum((line.total_ht for line in self.lines), Decimal(0))

    @property
    def total_vat(self):
        return sum(
            (
                (line.total_ht * line.vat / 100).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )
                for line in self.lines
            ),
            Decimal(0),
        )

    @property
    def total_ttc(self):
        return self.total_ht + self.total_vat

    def save(self, database: Database, notes="", service=""):
        if not self.lines:
            raise ValueError("Ajoutez un article avant d'enregistrer.")
        self.order_id = database.save_order(
            self.supplier_id,
            [line.as_mapping() for line in self.lines],
            notes=notes,
            order_id=self.order_id,
            requester_service=service,
        )
        self.dirty = False
        return self.order_id

    def load(self, database: Database, order_id):
        order, lines = database.get_order(order_id)
        if order["status"] != "Brouillon" or not database.can_delete_unsent_order(
            order
        ):
            raise ValueError(
                "Reprenez d'abord cette commande en brouillon depuis l'historique."
            )
        self.supplier_id, self.order_id = order["supplier_id"], order_id
        self.lines = [
            CartLine(
                row["product_id"],
                row["code_cahpp"],
                row["supplier_ref"],
                row["designation"],
                money(row["cartons"]),
                money(row["units_per_carton"]),
                money(row["unit_price"]),
                money(row["vat"]),
            )
            for row in lines
        ]
        self.dirty = False
        return dict(order)


class HorizonService:
    def __init__(self, database: Database):
        self.database = database

    def search(
        self,
        query="",
        supplier_id=None,
        favorite=False,
        review=False,
        limit=100,
        include_inactive=False,
        *,
        cancel,
        progress,
    ):
        return self.database.search_products_detailed(
            query=query,
            supplier_id=supplier_id,
            favorite_only=favorite,
            review_only=review,
            include_inactive=include_inactive,
            limit=limit,
            cancel_event=cancel,
        )

    def overview(self, *, cancel, progress):
        dashboard = self.database.dashboard_stats()
        with self.database.connect() as c:
            review = c.execute(
                "SELECT COUNT(*) FROM products p LEFT JOIN product_overrides po ON po.product_id=p.id WHERE p.active=1 AND "
                + CATALOG_REVIEW_SQL
            ).fetchone()[0]
            drafts = c.execute(
                "SELECT COUNT(*) FROM orders WHERE deleted_at='' AND archived_at='' AND sent_at='' AND status IN ('Brouillon','Générée','E-mail préparé')"
            ).fetchone()[0]
        stats = self.statistics(6, None, cancel=cancel, progress=progress)
        return {
            "dashboard": dashboard,
            "review": review,
            "drafts": drafts,
            "statistics": stats,
            "orders": [dict(r) for r in self.database.list_orders(limit=6)],
        }

    def statistics(self, months=6, supplier_id=None, *, cancel, progress):
        today = date.today()
        serial = today.year * 12 + today.month - 1
        first_serial = serial - months + 1
        first = date(first_serial // 12, first_serial % 12 + 1, 1)
        params = [first.isoformat(), today.isoformat()]
        clause = "deleted_at='' AND sent_at<>'' AND order_date BETWEEN ? AND ?"
        if supplier_id:
            clause += " AND supplier_id=?"
            params.append(supplier_id)
        with self.database.connect() as c:
            if cancel.is_set():
                return None
            totals = dict(
                c.execute(
                    f"SELECT COUNT(*) AS orders,COUNT(DISTINCT supplier_id) AS suppliers,COALESCE(SUM(total_ht),0) AS total_ht FROM orders WHERE {clause}",
                    params,
                ).fetchone()
            )
            monthly = {
                row["month"]: row["total_ht"]
                for row in c.execute(
                    f"SELECT substr(order_date,1,7) AS month,SUM(total_ht) AS total_ht FROM orders WHERE {clause} GROUP BY month",
                    params,
                )
            }
            suppliers = [
                dict(row)
                for row in c.execute(
                    f"SELECT s.id,s.name,COUNT(*) AS orders,SUM(o.total_ht) AS total_ht,AVG(CASE WHEN o.delivered_at<>'' THEN julianday(o.delivered_at)-julianday(o.sent_at) END) AS delivery_days FROM orders o JOIN suppliers s ON s.id=o.supplier_id WHERE {clause} GROUP BY s.id ORDER BY total_ht DESC",
                    params,
                )
            ]
        labels, values = [], []
        names = (
            "Janv.",
            "Févr.",
            "Mars",
            "Avr.",
            "Mai",
            "Juin",
            "Juil.",
            "Août",
            "Sept.",
            "Oct.",
            "Nov.",
            "Déc.",
        )
        for n in range(first_serial, serial + 1):
            labels.append(names[n % 12])
            values.append(monthly.get(f"{n // 12:04d}-{n % 12 + 1:02d}", 0))
        return {
            "totals": totals,
            "labels": labels,
            "values": values,
            "suppliers": suppliers,
        }

    def orders(self, query="", group="Toutes", *, cancel, progress):
        rows = [
            dict(r)
            for r in self.database.list_orders(
                query=query, include_archived=False, limit=500
            )
        ]
        if group == "À préparer / envoyer":
            rows = [r for r in rows if not r["sent_at"]]
        elif group == "À recevoir":
            rows = [
                r for r in rows if r["sent_at"] and r["delivery_status"] != "Livrée"
            ]
        elif group == "Terminées":
            rows = [r for r in rows if r["delivery_status"] == "Livrée"]
        return rows


def seed_demo(database: Database):
    """Petit jeu fictif déterministe, exclusivement dans un profil de démonstration."""
    with database.connect() as c:
        if c.execute("SELECT 1 FROM products LIMIT 1").fetchone():
            return
    suppliers = []
    for name in (
        "Médilia — démonstration",
        "Carevia — démonstration",
        "Atelier Santé — démonstration",
    ):
        with database.session() as c:
            sid = c.execute(
                "INSERT INTO suppliers(name,franco_ht) VALUES (?,150)", (name,)
            ).lastrowid
        suppliers.append(sid)
    ids = []
    definitions = [
        (0, "Gants d'examen nitrile — taille M", 100, 0.0421),
        (0, "Compresses non tissées 5 × 5 cm", 100, 0.0212),
        (1, "Alèses absorbantes 60 × 90 cm", 30, 0.46),
        (1, "Gants de toilette à usage unique", 50, 0.058),
        (0, "Solution hydroalcoolique 500 ml", 12, 3.45),
        (0, "Masques chirurgicaux type II", 50, 0.078),
        (1, "Protections anatomiques jour", 30, 0.58),
        (2, "Gobelets réutilisables 25 cl", 25, 1.2),
    ]
    for i, (supplier, name, pack, price) in enumerate(definitions, 1):
        pid = database.create_manual_product(
            suppliers[supplier], f"DEMO-{i:03d}", name, pack, price, 20
        )
        ids.append(pid)
        with database.session() as c:
            c.execute(
                "UPDATE products SET source='CAHPP',favorite=?,code_cahpp=? WHERE id=?",
                (int(i in (1, 2, 4)), f"DEMO-{i:04d}", pid),
            )
    serial = date.today().year * 12 + date.today().month - 1
    for n in range(6):
        period = serial - 5 + n
        for s, sid in enumerate(suppliers):
            pid = ids[[0, 2, 7][s]]
            p = database.get_product(pid)
            d = date(
                period // 12,
                period % 12 + 1,
                min(3 + s, date.today().day) if n == 5 else 3 + s,
            )
            oid = database.save_order(
                sid,
                [
                    {
                        "product_id": pid,
                        "code_cahpp": p["code_cahpp"],
                        "supplier_ref": p["supplier_ref"],
                        "designation": p["designation"],
                        "cartons": 12 + n * 3 + s,
                        "units_per_carton": p["conditionnement"],
                        "unit_price": p["unit_price"],
                        "vat": 20,
                    }
                ],
                selected_date=d,
            )
            database.update_order_status(oid, "Envoyée")
            with database.session() as c:
                c.execute(
                    "UPDATE orders SET sent_at=? WHERE id=?",
                    (d.isoformat() + "T10:00:00", oid),
                )
            if n < 5:
                database.update_delivery_status(oid, "Livrée")
                with database.session() as c:
                    c.execute(
                        "UPDATE orders SET delivered_at=? WHERE id=?",
                        ((d + timedelta(days=4 + s)).isoformat() + "T10:00:00", oid),
                    )
    database.save_order(
        suppliers[0],
        [
            {
                "product_id": ids[0],
                "designation": definitions[0][1],
                "cartons": 2,
                "units_per_carton": 100,
                "unit_price": 0.0421,
                "vat": 20,
            }
        ],
    )
    with database.session() as c:
        for pid in ids[5:7]:
            c.execute(
                "UPDATE products SET catalog_review_token=?,catalog_review_reason=? WHERE id=?",
                (
                    f"demo-review-{pid}",
                    "Conditionnement à vérifier auprès du fournisseur.",
                    pid,
                ),
            )
        c.execute(
            "UPDATE products SET conditionnement=NULL,qml=NULL WHERE id=?", (ids[6],)
        )
    database.rebuild_search()
    database.save_settings({"horizon_demo_seeded": "1"})
