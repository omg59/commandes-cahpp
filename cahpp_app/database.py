from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    file_hash TEXT NOT NULL UNIQUE,
    imported_at TEXT NOT NULL,
    row_count INTEGER NOT NULL DEFAULT 0,
    added_count INTEGER NOT NULL DEFAULT 0,
    updated_count INTEGER NOT NULL DEFAULT 0,
    missing_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cahpp_id INTEGER,
    name TEXT NOT NULL UNIQUE,
    customer_number TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    franco_ht REAL,
    notes TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_suppliers_name ON suppliers(name);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code_cahpp TEXT NOT NULL UNIQUE,
    catalogue TEXT NOT NULL DEFAULT '',
    supplier_id INTEGER REFERENCES suppliers(id),
    supplier_cahpp_id INTEGER,
    supplier_name TEXT NOT NULL DEFAULT '',
    supplier_ref TEXT NOT NULL DEFAULT '',
    designation TEXT NOT NULL DEFAULT '',
    acl TEXT NOT NULL DEFAULT '',
    acl13 TEXT NOT NULL DEFAULT '',
    cip13 TEXT NOT NULL DEFAULT '',
    ucd13 TEXT NOT NULL DEFAULT '',
    conditionnement REAL,
    qml REAL,
    vat REAL,
    unit_price REAL,
    gam_price REAL,
    classification_name TEXT NOT NULL DEFAULT '',
    classification_code TEXT NOT NULL DEFAULT '',
    evolution TEXT NOT NULL DEFAULT '',
    update_type TEXT NOT NULL DEFAULT '',
    update_state TEXT NOT NULL DEFAULT '',
    manufacturing_zone TEXT NOT NULL DEFAULT '',
    hazardous TEXT NOT NULL DEFAULT '',
    unit_packaging TEXT NOT NULL DEFAULT '',
    update_month TEXT NOT NULL DEFAULT '',
    gam_market TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL DEFAULT 'CAHPP',
    last_seen_import_id INTEGER REFERENCES imports(id),
    favorite INTEGER NOT NULL DEFAULT 0,
    usual_cartons REAL NOT NULL DEFAULT 1,
    short_name TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_products_supplier ON products(supplier_id, active);
CREATE INDEX IF NOT EXISTS idx_products_supplier_ref ON products(supplier_ref);
CREATE INDEX IF NOT EXISTS idx_products_favorite ON products(favorite, supplier_id);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id),
    import_id INTEGER NOT NULL REFERENCES imports(id),
    recorded_at TEXT NOT NULL,
    unit_price REAL,
    conditionnement REAL,
    qml REAL,
    UNIQUE(product_id, import_id)
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_number TEXT NOT NULL UNIQUE,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    order_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Brouillon',
    notes TEXT NOT NULL DEFAULT '',
    total_ht REAL NOT NULL DEFAULT 0,
    total_vat REAL NOT NULL DEFAULT 0,
    total_ttc REAL NOT NULL DEFAULT 0,
    pdf_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(order_date DESC);

CREATE TABLE IF NOT EXISTS order_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES products(id),
    code_cahpp TEXT NOT NULL DEFAULT '',
    supplier_ref TEXT NOT NULL DEFAULT '',
    designation TEXT NOT NULL,
    cartons REAL NOT NULL DEFAULT 0,
    units_per_carton REAL NOT NULL DEFAULT 0,
    total_units REAL NOT NULL DEFAULT 0,
    unit_price REAL NOT NULL DEFAULT 0,
    vat REAL NOT NULL DEFAULT 0,
    total_ht REAL NOT NULL DEFAULT 0,
    line_order INTEGER NOT NULL DEFAULT 0
);
"""


DEFAULT_SETTINGS = {
    "establishment_name": "",
    "establishment_subtitle": "",
    "address_line1": "",
    "address_line2": "",
    "postal_city": "",
    "phone": "",
    "email": "",
    "finess": "",
    "siret": "",
    "ape": "",
    "logo_path": "",
    "pdf_title": "BON DE COMMANDE",
    "pdf_footer_text": "",
    "pdf_show_page_number": "1",
    "pdf_default_directory": "",
}


def money(value: Decimal | float | int | str | None) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fts_available = True
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.session() as connection:
            connection.executescript(SCHEMA)
            try:
                connection.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS product_search USING fts5(
                        code_cahpp,
                        supplier_ref,
                        designation,
                        supplier_name,
                        tokenize='unicode61 remove_diacritics 2'
                    )
                    """
                )
            except sqlite3.OperationalError:
                self.fts_available = False
            connection.executemany(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                DEFAULT_SETTINGS.items(),
            )

    def dashboard_stats(self) -> dict[str, object]:
        with self.connect() as connection:
            stats = {
                "products": connection.execute(
                    "SELECT COUNT(*) FROM products WHERE active = 1"
                ).fetchone()[0],
                "suppliers": connection.execute(
                    "SELECT COUNT(*) FROM suppliers"
                ).fetchone()[0],
                "favorites": connection.execute(
                    "SELECT COUNT(*) FROM products WHERE favorite = 1"
                ).fetchone()[0],
                "orders": connection.execute(
                    "SELECT COUNT(*) FROM orders"
                ).fetchone()[0],
            }
            latest = connection.execute(
                "SELECT filename, imported_at, row_count FROM imports ORDER BY id DESC LIMIT 1"
            ).fetchone()
            stats["latest_import"] = dict(latest) if latest else None
            return stats

    def get_settings(self) -> dict[str, str]:
        with self.connect() as connection:
            return {
                row["key"]: row["value"]
                for row in connection.execute("SELECT key, value FROM settings")
            }

    def save_settings(self, values: Mapping[str, str]) -> None:
        with self.session() as connection:
            connection.executemany(
                """
                INSERT INTO settings(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                ((key, str(value or "").strip()) for key, value in values.items()),
            )

    def list_suppliers(self, used_only: bool = False) -> list[sqlite3.Row]:
        where = ""
        if used_only:
            where = """
            WHERE EXISTS (
                SELECT 1 FROM products p
                WHERE p.supplier_id = suppliers.id AND p.active = 1
            )
            """
        with self.connect() as connection:
            return list(
                connection.execute(
                    f"""
                    SELECT id, cahpp_id, name, customer_number, email, phone,
                           franco_ht, notes
                    FROM suppliers
                    {where}
                    ORDER BY name COLLATE NOCASE
                    """
                )
            )

    def get_supplier(self, supplier_id: int) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(
                "SELECT * FROM suppliers WHERE id = ?", (supplier_id,)
            ).fetchone()

    def update_supplier(
        self,
        supplier_id: int,
        customer_number: str,
        email: str,
        phone: str,
        franco_ht: float | None,
        notes: str,
    ) -> None:
        with self.session() as connection:
            connection.execute(
                """
                UPDATE suppliers
                SET customer_number = ?, email = ?, phone = ?, franco_ht = ?,
                    notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    customer_number.strip(),
                    email.strip(),
                    phone.strip(),
                    franco_ht,
                    notes.strip(),
                    datetime.now().isoformat(timespec="seconds"),
                    supplier_id,
                ),
            )

    @staticmethod
    def _fts_query(query: str) -> str:
        terms = re.findall(r"[\w]+", query, flags=re.UNICODE)
        return " AND ".join(f'"{term}"*' for term in terms[:10])

    def search_products(
        self,
        query: str = "",
        supplier_id: int | None = None,
        favorite_only: bool = False,
        limit: int = 200,
        include_inactive: bool = False,
    ) -> list[sqlite3.Row]:
        filters = []
        parameters: list[object] = []
        if not include_inactive:
            filters.append("p.active = 1")
        if supplier_id:
            filters.append("p.supplier_id = ?")
            parameters.append(supplier_id)
        if favorite_only:
            filters.append("p.favorite = 1")
        where = " AND ".join(filters) if filters else "1 = 1"
        query = query.strip()

        with self.connect() as connection:
            if query and self.fts_available:
                fts = self._fts_query(query)
                if fts:
                    sql = f"""
                        SELECT p.*
                        FROM product_search
                        JOIN products p ON p.id = product_search.rowid
                        WHERE product_search MATCH ? AND {where}
                        ORDER BY p.favorite DESC, bm25(product_search), p.designation
                        LIMIT ?
                    """
                    return list(connection.execute(sql, [fts, *parameters, limit]))

            if query:
                like = f"%{query}%"
                where += """
                    AND (
                        p.code_cahpp LIKE ? OR p.supplier_ref LIKE ?
                        OR p.designation LIKE ? OR p.supplier_name LIKE ?
                    )
                """
                parameters.extend([like, like, like, like])
            return list(
                connection.execute(
                    f"""
                    SELECT p.*
                    FROM products p
                    WHERE {where}
                    ORDER BY p.favorite DESC, p.supplier_name, p.designation
                    LIMIT ?
                    """,
                    [*parameters, limit],
                )
            )

    def get_product(self, product_id: int) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(
                "SELECT * FROM products WHERE id = ?", (product_id,)
            ).fetchone()

    def set_favorite(
        self,
        product_id: int,
        favorite: bool,
        usual_cartons: float | None = None,
        short_name: str | None = None,
    ) -> None:
        sets = ["favorite = ?", "updated_at = ?"]
        values: list[object] = [
            int(favorite),
            datetime.now().isoformat(timespec="seconds"),
        ]
        if usual_cartons is not None:
            sets.append("usual_cartons = ?")
            values.append(usual_cartons)
        if short_name is not None:
            sets.append("short_name = ?")
            values.append(short_name.strip())
        values.append(product_id)
        with self.session() as connection:
            connection.execute(
                f"UPDATE products SET {', '.join(sets)} WHERE id = ?", values
            )

    def create_manual_product(
        self,
        supplier_id: int,
        supplier_ref: str,
        designation: str,
        conditionnement: float,
        unit_price: float,
        vat: float,
    ) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        code = f"LOCAL-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        supplier = self.get_supplier(supplier_id)
        if supplier is None:
            raise ValueError("Fournisseur introuvable")
        with self.session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO products(
                    code_cahpp, supplier_id, supplier_cahpp_id, supplier_name, supplier_ref,
                    designation, conditionnement, qml, vat, unit_price,
                    active, source, favorite, usual_cartons, created_at, updated_at
                ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, 1, 'LOCAL', 1, 1, ?, ?)
                """,
                (
                    code,
                    supplier_id,
                    supplier["name"],
                    supplier_ref.strip(),
                    designation.strip(),
                    conditionnement,
                    conditionnement,
                    vat,
                    unit_price,
                    now,
                    now,
                ),
            )
            product_id = cursor.lastrowid
            self._add_product_to_search(connection, product_id)
            return int(product_id)

    @staticmethod
    def _add_product_to_search(
        connection: sqlite3.Connection, product_id: int
    ) -> None:
        try:
            connection.execute(
                """
                INSERT INTO product_search(
                    rowid, code_cahpp, supplier_ref, designation, supplier_name
                )
                SELECT id, code_cahpp, supplier_ref, designation, supplier_name
                FROM products WHERE id = ?
                """,
                (product_id,),
            )
        except sqlite3.OperationalError:
            pass

    def _next_order_number(
        self, connection: sqlite3.Connection, order_date: date
    ) -> str:
        prefix = f"BC-{order_date.year}-"
        row = connection.execute(
            """
            SELECT order_number FROM orders
            WHERE order_number LIKE ?
            ORDER BY order_number DESC LIMIT 1
            """,
            (prefix + "%",),
        ).fetchone()
        sequence = int(row["order_number"].split("-")[-1]) + 1 if row else 1
        return f"{prefix}{sequence:04d}"

    def save_order(
        self,
        supplier_id: int,
        lines: Sequence[Mapping[str, object]],
        notes: str = "",
        status: str = "Brouillon",
        order_id: int | None = None,
        selected_date: date | None = None,
    ) -> int:
        if not lines:
            raise ValueError("La commande ne contient aucune ligne.")
        selected_date = selected_date or date.today()
        now = datetime.now().isoformat(timespec="seconds")
        total_ht = Decimal("0")
        total_vat = Decimal("0")
        normalized_lines = []
        for index, line in enumerate(lines):
            cartons = money(line.get("cartons"))
            units_per_carton = money(line.get("units_per_carton"))
            unit_price = money(line.get("unit_price"))
            vat = money(line.get("vat"))
            total_units = cartons * units_per_carton
            line_ht = (total_units * unit_price).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
            line_vat = (line_ht * vat / Decimal("100")).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
            total_ht += line_ht
            total_vat += line_vat
            normalized_lines.append(
                (
                    line.get("product_id"),
                    str(line.get("code_cahpp") or ""),
                    str(line.get("supplier_ref") or ""),
                    str(line.get("designation") or ""),
                    float(cartons),
                    float(units_per_carton),
                    float(total_units),
                    float(unit_price),
                    float(vat),
                    float(line_ht),
                    index,
                )
            )
        total_ttc = total_ht + total_vat

        with self.session() as connection:
            if order_id is None:
                order_number = self._next_order_number(connection, selected_date)
                cursor = connection.execute(
                    """
                    INSERT INTO orders(
                        order_number, supplier_id, order_date, status, notes,
                        total_ht, total_vat, total_ttc, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_number,
                        supplier_id,
                        selected_date.isoformat(),
                        status,
                        notes.strip(),
                        float(total_ht),
                        float(total_vat),
                        float(total_ttc),
                        now,
                        now,
                    ),
                )
                order_id = int(cursor.lastrowid)
            else:
                connection.execute(
                    """
                    UPDATE orders
                    SET supplier_id = ?, order_date = ?, status = ?, notes = ?,
                        total_ht = ?, total_vat = ?, total_ttc = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        supplier_id,
                        selected_date.isoformat(),
                        status,
                        notes.strip(),
                        float(total_ht),
                        float(total_vat),
                        float(total_ttc),
                        now,
                        order_id,
                    ),
                )
                connection.execute(
                    "DELETE FROM order_lines WHERE order_id = ?", (order_id,)
                )
            connection.executemany(
                """
                INSERT INTO order_lines(
                    order_id, product_id, code_cahpp, supplier_ref, designation,
                    cartons, units_per_carton, total_units, unit_price, vat,
                    total_ht, line_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ((order_id, *line) for line in normalized_lines),
            )
        return int(order_id)

    def list_orders(self, limit: int = 500) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT o.*, s.name AS supplier_name
                    FROM orders o
                    JOIN suppliers s ON s.id = o.supplier_id
                    ORDER BY o.order_date DESC, o.id DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            )

    def get_order(self, order_id: int) -> tuple[sqlite3.Row, list[sqlite3.Row]]:
        with self.connect() as connection:
            order = connection.execute(
                """
                SELECT o.*, s.name AS supplier_name, s.customer_number,
                       s.email AS supplier_email, s.phone AS supplier_phone,
                       s.franco_ht, s.notes AS supplier_notes
                FROM orders o
                JOIN suppliers s ON s.id = o.supplier_id
                WHERE o.id = ?
                """,
                (order_id,),
            ).fetchone()
            if order is None:
                raise ValueError("Commande introuvable")
            lines = list(
                connection.execute(
                    """
                    SELECT * FROM order_lines
                    WHERE order_id = ?
                    ORDER BY line_order, id
                    """,
                    (order_id,),
                )
            )
            return order, lines

    def daily_supplier_order_sequence(self, order_id: int) -> int:
        with self.connect() as connection:
            order = connection.execute(
                """
                SELECT id, supplier_id, order_date
                FROM orders
                WHERE id = ?
                """,
                (order_id,),
            ).fetchone()
            if order is None:
                raise ValueError("Commande introuvable")
            return int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM orders
                    WHERE supplier_id = ?
                      AND order_date = ?
                      AND id <= ?
                    """,
                    (
                        order["supplier_id"],
                        order["order_date"],
                        order["id"],
                    ),
                ).fetchone()[0]
            )

    def update_order_pdf(self, order_id: int, pdf_path: str) -> None:
        with self.session() as connection:
            connection.execute(
                """
                UPDATE orders
                SET pdf_path = ?, status = 'Générée', updated_at = ?
                WHERE id = ?
                """,
                (
                    pdf_path,
                    datetime.now().isoformat(timespec="seconds"),
                    order_id,
                ),
            )

    def latest_imports(self, limit: int = 20) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT * FROM imports ORDER BY id DESC LIMIT ?
                    """,
                    (limit,),
                )
            )

    def favorite_changes_for_import(self, import_id: int) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT p.code_cahpp, p.supplier_name, p.supplier_ref,
                           p.designation, p.active, ph.unit_price,
                           ph.conditionnement, ph.qml
                    FROM price_history ph
                    JOIN products p ON p.id = ph.product_id
                    WHERE ph.import_id = ? AND p.favorite = 1
                    ORDER BY p.supplier_name, p.designation
                    """,
                    (import_id,),
                )
            )

    def rebuild_search(self, connection: sqlite3.Connection | None = None) -> None:
        owns_connection = connection is None
        connection = connection or self.connect()
        try:
            connection.execute("DELETE FROM product_search")
            connection.execute(
                """
                INSERT INTO product_search(
                    rowid, code_cahpp, supplier_ref, designation, supplier_name
                )
                SELECT id, code_cahpp, supplier_ref, designation, supplier_name
                FROM products
                """
            )
            if owns_connection:
                connection.commit()
        except sqlite3.OperationalError:
            self.fts_available = False
        finally:
            if owns_connection:
                connection.close()

    def backup(self, destination: Path | str) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = self.connect()
        target = sqlite3.connect(destination)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        return destination
