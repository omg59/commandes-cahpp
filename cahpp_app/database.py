from __future__ import annotations

import re
import sqlite3
import uuid
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
    contact_name TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    website TEXT NOT NULL DEFAULT '',
    franco_ht REAL,
    minimum_order_ht REAL,
    notes TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    updated_by TEXT NOT NULL DEFAULT ''
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
    created_by TEXT NOT NULL DEFAULT '',
    updated_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_products_supplier ON products(supplier_id, active);
CREATE INDEX IF NOT EXISTS idx_products_supplier_ref ON products(supplier_ref);
CREATE INDEX IF NOT EXISTS idx_products_favorite ON products(favorite, supplier_id);

CREATE TABLE IF NOT EXISTS product_overrides (
    product_id INTEGER PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE,
    supplier_ref TEXT,
    designation TEXT,
    conditionnement REAL,
    unit_packaging TEXT,
    unit_price REAL,
    vat REAL,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS product_team_state (
    code_cahpp TEXT PRIMARY KEY,
    favorite INTEGER NOT NULL DEFAULT 0,
    usual_cartons REAL NOT NULL DEFAULT 1,
    short_name TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL DEFAULT ''
);

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
    email_prepared_at TEXT NOT NULL DEFAULT '',
    sent_at TEXT NOT NULL DEFAULT '',
    shared_uid TEXT NOT NULL DEFAULT '',
    shared_revision INTEGER NOT NULL DEFAULT 0,
    sync_state TEXT NOT NULL DEFAULT 'Local',
    catalog_hash TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    updated_by TEXT NOT NULL DEFAULT '',
    sent_by TEXT NOT NULL DEFAULT '',
    last_synced_at TEXT NOT NULL DEFAULT '',
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

CREATE TABLE IF NOT EXISTS order_attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    kind TEXT NOT NULL DEFAULT 'Pièce jointe',
    display_name TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    include_in_email INTEGER NOT NULL DEFAULT 0,
    added_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_order_attachments_order
ON order_attachments(order_id, added_at);

CREATE TABLE IF NOT EXISTS order_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_uid TEXT NOT NULL UNIQUE,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    actor_id TEXT NOT NULL DEFAULT '',
    actor_name TEXT NOT NULL DEFAULT '',
    occurred_at TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_order_audit_order
ON order_audit(order_id, occurred_at);
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
    "mail_compose_url": "https://mail.google.com/mail/?view=cm&fs=1",
    "email_subject_template": "Bon de commande {order_number} - {supplier}",
    "email_body_template": (
        "Bonjour,\n\n"
        "Veuillez trouver ci-joint notre bon de commande {order_number}.\n\n"
        "Cordialement,\n{establishment_name}"
    ),
    "user_id": "",
    "user_name": "",
    "collaboration_enabled": "0",
    "shared_workspace_path": "",
    "collaboration_workspace_id": "",
    "collaboration_last_sync_at": "",
    "collaboration_catalog_hash": "",
    "collaboration_catalog_version": "",
    "team_settings_updated_at": "",
    "team_settings_updated_by": "",
}

TEAM_SETTING_KEYS = (
    "establishment_name",
    "establishment_subtitle",
    "address_line1",
    "address_line2",
    "postal_city",
    "phone",
    "email",
    "finess",
    "siret",
    "ape",
    "pdf_title",
    "pdf_footer_text",
    "pdf_show_page_number",
    "email_subject_template",
    "email_body_template",
)

PRODUCT_OVERRIDE_FIELDS = (
    "supplier_ref",
    "designation",
    "conditionnement",
    "unit_packaging",
    "unit_price",
    "vat",
)

PRODUCT_SELECT = """
    p.*,
    po.supplier_ref AS override_supplier_ref,
    po.designation AS override_designation,
    po.conditionnement AS override_conditionnement,
    po.unit_packaging AS override_unit_packaging,
    po.unit_price AS override_unit_price,
    po.vat AS override_vat
"""


def money(value: Decimal | float | int | str | None) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fts_available = True
        self.current_user_id = ""
        self.current_user_name = "Utilisateur"
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
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
        # Le mode WAL est configuré une seule fois. Le répéter à chaque
        # recherche provoquait des verrouillages coûteux, surtout lorsque
        # l'application avait été copiée sur un partage réseau.
        with sqlite3.connect(self.path, timeout=30) as bootstrap:
            bootstrap.execute("PRAGMA busy_timeout = 30000")
            bootstrap.execute("PRAGMA journal_mode = WAL")
        with self.session() as connection:
            connection.executescript(SCHEMA)
            self._migrate_schema(connection)
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
            connection.execute("PRAGMA user_version = 9")

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table: str,
        column: str,
        declaration: str,
    ) -> None:
        columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table})")
        }
        if column not in columns:
            connection.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {declaration}"
            )

    def _migrate_schema(self, connection: sqlite3.Connection) -> None:
        """Ajoute sans perte les champs apparus après le prototype 0.4."""
        for column, declaration in (
            ("contact_name", "TEXT NOT NULL DEFAULT ''"),
            ("address", "TEXT NOT NULL DEFAULT ''"),
            ("website", "TEXT NOT NULL DEFAULT ''"),
            ("minimum_order_ht", "REAL"),
            ("updated_by", "TEXT NOT NULL DEFAULT ''"),
        ):
            self._ensure_column(connection, "suppliers", column, declaration)
        for column, declaration in (
            ("email_prepared_at", "TEXT NOT NULL DEFAULT ''"),
            ("sent_at", "TEXT NOT NULL DEFAULT ''"),
            ("shared_uid", "TEXT NOT NULL DEFAULT ''"),
            ("shared_revision", "INTEGER NOT NULL DEFAULT 0"),
            ("sync_state", "TEXT NOT NULL DEFAULT 'Local'"),
            ("catalog_hash", "TEXT NOT NULL DEFAULT ''"),
            ("created_by", "TEXT NOT NULL DEFAULT ''"),
            ("updated_by", "TEXT NOT NULL DEFAULT ''"),
            ("sent_by", "TEXT NOT NULL DEFAULT ''"),
            ("last_synced_at", "TEXT NOT NULL DEFAULT ''"),
        ):
            self._ensure_column(connection, "orders", column, declaration)
        for column, declaration in (
            ("created_by", "TEXT NOT NULL DEFAULT ''"),
            ("updated_by", "TEXT NOT NULL DEFAULT ''"),
        ):
            self._ensure_column(connection, "products", column, declaration)
        self._ensure_column(
            connection,
            "product_overrides",
            "updated_by",
            "TEXT NOT NULL DEFAULT ''",
        )
        legacy_mail_url = connection.execute(
            "SELECT value FROM settings WHERE key = 'gmail_compose_url'"
        ).fetchone()
        current_mail_url = connection.execute(
            "SELECT value FROM settings WHERE key = 'mail_compose_url'"
        ).fetchone()
        if legacy_mail_url and (
            current_mail_url is None or not current_mail_url["value"].strip()
        ):
            connection.execute(
                """
                INSERT INTO settings(key, value) VALUES ('mail_compose_url', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (legacy_mail_url["value"],),
            )
        existing_orders = connection.execute(
            "SELECT id FROM orders WHERE shared_uid = ''"
        ).fetchall()
        for row in existing_orders:
            connection.execute(
                """
                UPDATE orders
                SET shared_uid = ?, shared_revision = MAX(shared_revision, 1),
                    sync_state = 'À synchroniser'
                WHERE id = ?
                """,
                (str(uuid.uuid4()), row["id"]),
            )
        connection.execute(
            """
            INSERT OR IGNORE INTO product_team_state(
                code_cahpp, favorite, usual_cartons, short_name,
                updated_at, updated_by
            )
            SELECT code_cahpp, favorite, usual_cartons, short_name,
                   updated_at, updated_by
            FROM products
            WHERE favorite <> 0 OR usual_cartons <> 1 OR short_name <> ''
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_shared_uid
            ON orders(shared_uid) WHERE shared_uid <> ''
            """
        )

    def set_current_user(self, user_id: str, user_name: str) -> None:
        self.current_user_id = user_id.strip()
        self.current_user_name = user_name.strip() or "Utilisateur"

    def _actor(self) -> tuple[str, str]:
        return self.current_user_id, self.current_user_name

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
        prepared = {
            key: str(value or "").strip() for key, value in values.items()
        }
        if any(key in TEAM_SETTING_KEYS for key in prepared):
            prepared.setdefault(
                "team_settings_updated_at",
                datetime.now().isoformat(timespec="seconds"),
            )
            prepared.setdefault(
                "team_settings_updated_by", self.current_user_name
            )
        with self.session() as connection:
            connection.executemany(
                """
                INSERT INTO settings(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                prepared.items(),
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
                           contact_name, address, website, franco_ht,
                           minimum_order_ht, notes
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
        contact_name: str = "",
        address: str = "",
        website: str = "",
        minimum_order_ht: float | None = None,
    ) -> None:
        _, actor_name = self._actor()
        with self.session() as connection:
            connection.execute(
                """
                UPDATE suppliers
                SET customer_number = ?, contact_name = ?, email = ?, phone = ?,
                    address = ?, website = ?, franco_ht = ?,
                    minimum_order_ht = ?, notes = ?, updated_at = ?,
                    updated_by = ?
                WHERE id = ?
                """,
                (
                    customer_number.strip(),
                    contact_name.strip(),
                    email.strip(),
                    phone.strip(),
                    address.strip(),
                    website.strip(),
                    franco_ht,
                    minimum_order_ht,
                    notes.strip(),
                    datetime.now().isoformat(timespec="seconds"),
                    actor_name,
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
    ) -> list[dict[str, object]]:
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
                        SELECT {PRODUCT_SELECT}
                        FROM product_search
                        JOIN products p ON p.id = product_search.rowid
                        LEFT JOIN product_overrides po ON po.product_id = p.id
                        WHERE product_search MATCH ? AND {where}
                        ORDER BY p.favorite DESC, bm25(product_search),
                                 COALESCE(po.designation, p.designation)
                        LIMIT ?
                    """
                    rows = connection.execute(
                        sql, [fts, *parameters, limit]
                    )
                    return [self._effective_product(row) for row in rows]

            if query:
                like = f"%{query}%"
                where += """
                    AND (
                        p.code_cahpp LIKE ?
                        OR COALESCE(po.supplier_ref, p.supplier_ref) LIKE ?
                        OR COALESCE(po.designation, p.designation) LIKE ?
                        OR p.supplier_name LIKE ?
                    )
                """
                parameters.extend([like, like, like, like])
            rows = connection.execute(
                f"""
                SELECT {PRODUCT_SELECT}
                FROM products p
                LEFT JOIN product_overrides po ON po.product_id = p.id
                WHERE {where}
                ORDER BY p.favorite DESC, p.supplier_name,
                         COALESCE(po.designation, p.designation)
                LIMIT ?
                """,
                [*parameters, limit],
            )
            return [self._effective_product(row) for row in rows]

    @staticmethod
    def _effective_product(row: sqlite3.Row) -> dict[str, object]:
        product = dict(row)
        has_override = False
        for field in PRODUCT_OVERRIDE_FIELDS:
            product[f"catalog_{field}"] = product[field]
            override = product.get(f"override_{field}")
            if override is not None:
                product[field] = override
                has_override = True
        product["has_override"] = has_override
        return product

    def get_product(self, product_id: int) -> dict[str, object] | None:
        with self.connect() as connection:
            row = connection.execute(
                f"""
                SELECT {PRODUCT_SELECT}
                FROM products p
                LEFT JOIN product_overrides po ON po.product_id = p.id
                WHERE p.id = ?
                """,
                (product_id,),
            ).fetchone()
            return self._effective_product(row) if row else None

    def set_favorite(
        self,
        product_id: int,
        favorite: bool,
        usual_cartons: float | None = None,
        short_name: str | None = None,
    ) -> None:
        _, actor_name = self._actor()
        updated_at = datetime.now().isoformat(timespec="seconds")
        sets = ["favorite = ?", "updated_at = ?"]
        values: list[object] = [
            int(favorite),
            updated_at,
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
            product = connection.execute(
                """
                SELECT code_cahpp, favorite, usual_cartons, short_name
                FROM products WHERE id = ?
                """,
                (product_id,),
            ).fetchone()
            if product is not None:
                connection.execute(
                    """
                    INSERT INTO product_team_state(
                        code_cahpp, favorite, usual_cartons, short_name,
                        updated_at, updated_by
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(code_cahpp) DO UPDATE SET
                        favorite = excluded.favorite,
                        usual_cartons = excluded.usual_cartons,
                        short_name = excluded.short_name,
                        updated_at = excluded.updated_at,
                        updated_by = excluded.updated_by
                    """,
                    (
                        product["code_cahpp"],
                        product["favorite"],
                        product["usual_cartons"],
                        product["short_name"],
                        updated_at,
                        actor_name,
                    ),
                )

    def create_manual_product(
        self,
        supplier_id: int,
        supplier_ref: str,
        designation: str,
        conditionnement: float,
        unit_price: float,
        vat: float,
        unit_packaging: str = "",
    ) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        _, actor_name = self._actor()
        code = f"LOCAL-{uuid.uuid4()}"
        supplier = self.get_supplier(supplier_id)
        if supplier is None:
            raise ValueError("Fournisseur introuvable")
        with self.session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO products(
                    code_cahpp, supplier_id, supplier_cahpp_id, supplier_name, supplier_ref,
                    designation, conditionnement, qml, vat, unit_price,
                    unit_packaging, active, source, favorite, usual_cartons,
                    created_by, updated_by, created_at, updated_at
                ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'LOCAL', 1, 1,
                          ?, ?, ?, ?)
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
                    unit_packaging.strip(),
                    actor_name,
                    actor_name,
                    now,
                    now,
                ),
            )
            product_id = cursor.lastrowid
            connection.execute(
                """
                INSERT INTO product_team_state(
                    code_cahpp, favorite, usual_cartons, short_name,
                    updated_at, updated_by
                ) VALUES (?, 1, 1, '', ?, ?)
                """,
                (code, now, actor_name),
            )
            self._add_product_to_search(connection, product_id)
            return int(product_id)

    def update_manual_product(
        self,
        product_id: int,
        supplier_ref: str,
        designation: str,
        conditionnement: float,
        unit_packaging: str,
        unit_price: float,
        vat: float,
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        _, actor_name = self._actor()
        with self.session() as connection:
            product = connection.execute(
                "SELECT source FROM products WHERE id = ?", (product_id,)
            ).fetchone()
            if product is None or product["source"] != "LOCAL":
                raise ValueError("Cette référence n'est pas un article local.")
            connection.execute(
                """
                UPDATE products
                SET supplier_ref = ?, designation = ?, conditionnement = ?,
                    qml = ?, unit_packaging = ?, unit_price = ?, vat = ?,
                    updated_at = ?, updated_by = ?
                WHERE id = ?
                """,
                (
                    supplier_ref.strip(),
                    designation.strip(),
                    conditionnement,
                    conditionnement,
                    unit_packaging.strip(),
                    unit_price,
                    vat,
                    now,
                    actor_name,
                    product_id,
                ),
            )
            self._add_product_to_search(connection, product_id)

    def archive_manual_product(self, product_id: int) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        _, actor_name = self._actor()
        with self.session() as connection:
            product = connection.execute(
                "SELECT source FROM products WHERE id = ?", (product_id,)
            ).fetchone()
            if product is None or product["source"] != "LOCAL":
                raise ValueError("Seules les références locales sont supprimables.")
            connection.execute(
                """
                UPDATE products
                SET active = 0, favorite = 0, updated_at = ?, updated_by = ?
                WHERE id = ?
                """,
                (now, actor_name, product_id),
            )
            code = connection.execute(
                "SELECT code_cahpp FROM products WHERE id = ?", (product_id,)
            ).fetchone()
            if code is not None:
                connection.execute(
                    """
                    INSERT INTO product_team_state(
                        code_cahpp, favorite, usual_cartons, short_name,
                        updated_at, updated_by
                    ) VALUES (?, 0, 1, '', ?, ?)
                    ON CONFLICT(code_cahpp) DO UPDATE SET
                        favorite = 0, updated_at = excluded.updated_at,
                        updated_by = excluded.updated_by
                    """,
                    (code["code_cahpp"], now, actor_name),
                )
            self._remove_product_from_search(connection, product_id)

    def set_product_override(
        self,
        product_id: int,
        supplier_ref: str,
        designation: str,
        conditionnement: float,
        unit_packaging: str,
        unit_price: float,
        vat: float,
    ) -> None:
        product = self.get_product(product_id)
        if product is None or product["source"] != "CAHPP":
            raise ValueError("Cette référence n'est pas issue du catalogue CAHPP.")

        edited: dict[str, object] = {
            "supplier_ref": supplier_ref.strip(),
            "designation": designation.strip(),
            "conditionnement": conditionnement,
            "unit_packaging": unit_packaging.strip(),
            "unit_price": unit_price,
            "vat": vat,
        }
        overrides: dict[str, object | None] = {}
        for field, value in edited.items():
            catalog_value = product[f"catalog_{field}"]
            if field in {"conditionnement", "unit_price", "vat"}:
                same = money(value) == money(catalog_value)
            else:
                same = str(value or "").strip() == str(
                    catalog_value or ""
                ).strip()
            overrides[field] = None if same else value

        now = datetime.now().isoformat(timespec="seconds")
        _, actor_name = self._actor()
        with self.session() as connection:
            connection.execute(
                """
                INSERT INTO product_overrides(
                    product_id, supplier_ref, designation, conditionnement,
                    unit_packaging, unit_price, vat, updated_at, updated_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(product_id) DO UPDATE SET
                    supplier_ref = excluded.supplier_ref,
                    designation = excluded.designation,
                    conditionnement = excluded.conditionnement,
                    unit_packaging = excluded.unit_packaging,
                    unit_price = excluded.unit_price,
                    vat = excluded.vat,
                    updated_at = excluded.updated_at,
                    updated_by = excluded.updated_by
                """,
                (
                    product_id,
                    overrides["supplier_ref"],
                    overrides["designation"],
                    overrides["conditionnement"],
                    overrides["unit_packaging"],
                    overrides["unit_price"],
                    overrides["vat"],
                    now,
                    actor_name,
                ),
            )
            connection.execute(
                """
                UPDATE products SET updated_at = ?, updated_by = ?
                WHERE id = ?
                """,
                (now, actor_name, product_id),
            )
            self._add_product_to_search(connection, product_id)

    def reset_product_override(self, product_id: int) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        _, actor_name = self._actor()
        with self.session() as connection:
            connection.execute(
                """
                INSERT INTO product_overrides(
                    product_id, supplier_ref, designation, conditionnement,
                    unit_packaging, unit_price, vat, updated_at, updated_by
                ) VALUES (?, NULL, NULL, NULL, NULL, NULL, NULL, ?, ?)
                ON CONFLICT(product_id) DO UPDATE SET
                    supplier_ref = NULL, designation = NULL,
                    conditionnement = NULL, unit_packaging = NULL,
                    unit_price = NULL, vat = NULL,
                    updated_at = excluded.updated_at,
                    updated_by = excluded.updated_by
                """,
                (product_id, now, actor_name),
            )
            connection.execute(
                """
                UPDATE products SET updated_at = ?, updated_by = ?
                WHERE id = ?
                """,
                (now, actor_name, product_id),
            )
            self._add_product_to_search(connection, product_id)

    @staticmethod
    def _add_product_to_search(
        connection: sqlite3.Connection, product_id: int
    ) -> None:
        try:
            connection.execute(
                "DELETE FROM product_search WHERE rowid = ?", (product_id,)
            )
            connection.execute(
                """
                INSERT INTO product_search(
                    rowid, code_cahpp, supplier_ref, designation, supplier_name
                )
                SELECT p.id, p.code_cahpp,
                       COALESCE(po.supplier_ref, p.supplier_ref),
                       COALESCE(po.designation, p.designation),
                       p.supplier_name
                FROM products p
                LEFT JOIN product_overrides po ON po.product_id = p.id
                WHERE p.id = ?
                """,
                (product_id,),
            )
        except sqlite3.OperationalError:
            pass

    @staticmethod
    def _remove_product_from_search(
        connection: sqlite3.Connection, product_id: int
    ) -> None:
        try:
            connection.execute(
                "DELETE FROM product_search WHERE rowid = ?", (product_id,)
            )
        except sqlite3.OperationalError:
            pass

    def _record_order_audit(
        self,
        connection: sqlite3.Connection,
        order_id: int,
        action: str,
        details: str = "",
        occurred_at: str | None = None,
        event_uid: str | None = None,
        actor_id: str | None = None,
        actor_name: str | None = None,
    ) -> None:
        current_id, current_name = self._actor()
        connection.execute(
            """
            INSERT OR IGNORE INTO order_audit(
                event_uid, order_id, action, actor_id, actor_name,
                occurred_at, details
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_uid or str(uuid.uuid4()),
                order_id,
                action,
                current_id if actor_id is None else actor_id,
                current_name if actor_name is None else actor_name,
                occurred_at or datetime.now().isoformat(timespec="seconds"),
                details,
            ),
        )

    def _touch_order(
        self,
        connection: sqlite3.Connection,
        order_id: int,
        now: str | None = None,
    ) -> None:
        _, actor_name = self._actor()
        connection.execute(
            """
            UPDATE orders
            SET shared_revision = shared_revision + 1,
                sync_state = 'À synchroniser',
                updated_at = ?, updated_by = ?
            WHERE id = ?
            """,
            (
                now or datetime.now().isoformat(timespec="seconds"),
                actor_name,
                order_id,
            ),
        )

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
        order_number: str | None = None,
        shared_uid: str | None = None,
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
        _, actor_name = self._actor()
        settings = self.get_settings()
        catalog_hash = settings.get("collaboration_catalog_hash", "")
        is_new = order_id is None

        with self.session() as connection:
            if is_new:
                order_number = order_number or self._next_order_number(
                    connection, selected_date
                )
                shared_uid = shared_uid or str(uuid.uuid4())
                cursor = connection.execute(
                    """
                    INSERT INTO orders(
                        order_number, supplier_id, order_date, status, notes,
                        total_ht, total_vat, total_ttc, shared_uid,
                        shared_revision, sync_state, catalog_hash,
                        created_by, updated_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'À synchroniser',
                              ?, ?, ?, ?, ?)
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
                        shared_uid,
                        catalog_hash,
                        actor_name,
                        actor_name,
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
                        total_ht = ?, total_vat = ?, total_ttc = ?,
                        shared_revision = shared_revision + 1,
                        sync_state = 'À synchroniser', catalog_hash = ?,
                        updated_at = ?, updated_by = ?
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
                        catalog_hash,
                        now,
                        actor_name,
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
            self._record_order_audit(
                connection,
                int(order_id),
                "Commande créée" if is_new else "Brouillon modifié",
            )
        return int(order_id)

    def list_orders(
        self,
        query: str = "",
        status: str = "",
        limit: int = 500,
    ) -> list[sqlite3.Row]:
        filters = []
        parameters: list[object] = []
        query = query.strip()
        if query:
            like = f"%{query}%"
            filters.append(
                """
                (
                    o.order_number LIKE ? OR s.name LIKE ? OR o.notes LIKE ?
                    OR EXISTS (
                        SELECT 1 FROM order_lines ol
                        WHERE ol.order_id = o.id
                          AND (
                              ol.code_cahpp LIKE ? OR ol.supplier_ref LIKE ?
                              OR ol.designation LIKE ?
                          )
                    )
                )
                """
            )
            parameters.extend([like, like, like, like, like, like])
        if status:
            filters.append("o.status = ?")
            parameters.append(status)
        where = " AND ".join(filters) if filters else "1 = 1"
        with self.connect() as connection:
            return list(
                connection.execute(
                    f"""
                    SELECT o.*, s.name AS supplier_name
                    FROM orders o
                    JOIN suppliers s ON s.id = o.supplier_id
                    WHERE {where}
                    ORDER BY o.order_date DESC, o.id DESC
                    LIMIT ?
                    """,
                    [*parameters, limit],
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

    def list_order_audit(self, order_id: int) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT action, actor_name, occurred_at, details
                    FROM order_audit
                    WHERE order_id = ?
                    ORDER BY occurred_at DESC, id DESC
                    """,
                    (order_id,),
                )
            )

    def duplicate_order(
        self,
        order_id: int,
        selected_date: date | None = None,
        order_number: str | None = None,
        shared_uid: str | None = None,
    ) -> int:
        order, lines = self.get_order(order_id)
        duplicated_lines = [
            {
                "product_id": line["product_id"],
                "code_cahpp": line["code_cahpp"],
                "supplier_ref": line["supplier_ref"],
                "designation": line["designation"],
                "cartons": line["cartons"],
                "units_per_carton": line["units_per_carton"],
                "unit_price": line["unit_price"],
                "vat": line["vat"],
            }
            for line in lines
        ]
        return self.save_order(
            supplier_id=int(order["supplier_id"]),
            lines=duplicated_lines,
            notes=order["notes"] or "",
            status="Brouillon",
            selected_date=selected_date or date.today(),
            order_number=order_number,
            shared_uid=shared_uid,
        )

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
        now = datetime.now().isoformat(timespec="seconds")
        _, actor_name = self._actor()
        with self.session() as connection:
            connection.execute(
                """
                UPDATE orders
                SET pdf_path = ?, status = 'Générée',
                    shared_revision = shared_revision + 1,
                    sync_state = 'À synchroniser',
                    updated_at = ?, updated_by = ?
                WHERE id = ?
                """,
                (
                    pdf_path,
                    now,
                    actor_name,
                    order_id,
                ),
            )
            self._record_order_audit(
                connection, order_id, "PDF généré", occurred_at=now
            )

    def update_order_status(self, order_id: int, status: str) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        _, actor_name = self._actor()
        sets = [
            "status = ?",
            "updated_at = ?",
            "updated_by = ?",
            "shared_revision = shared_revision + 1",
            "sync_state = 'À synchroniser'",
        ]
        values: list[object] = [status, now, actor_name]
        if status == "E-mail préparé":
            sets.append("email_prepared_at = ?")
            values.append(now)
        if status == "Envoyée":
            sets.append(
                "sent_at = CASE WHEN sent_at = '' THEN ? ELSE sent_at END"
            )
            values.append(now)
            sets.append("sent_by = ?")
            values.append(actor_name)
        values.append(order_id)
        with self.session() as connection:
            connection.execute(
                f"UPDATE orders SET {', '.join(sets)} WHERE id = ?",
                values,
            )
            self._record_order_audit(
                connection,
                order_id,
                f"Statut : {status}",
                occurred_at=now,
            )

    def add_order_attachment(
        self,
        order_id: int,
        kind: str,
        display_name: str,
        stored_path: str,
        include_in_email: bool = False,
    ) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        with self.session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO order_attachments(
                    order_id, kind, display_name, stored_path,
                    include_in_email, added_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    kind.strip() or "Pièce jointe",
                    display_name.strip(),
                    stored_path,
                    int(include_in_email),
                    now,
                ),
            )
            self._touch_order(connection, order_id, now)
            self._record_order_audit(
                connection,
                order_id,
                f"Document ajouté : {display_name.strip()}",
                occurred_at=now,
            )
            return int(cursor.lastrowid)

    def list_order_attachments(self, order_id: int) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT * FROM order_attachments
                    WHERE order_id = ?
                    ORDER BY added_at, id
                    """,
                    (order_id,),
                )
            )

    def get_order_attachment(self, attachment_id: int) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(
                "SELECT * FROM order_attachments WHERE id = ?",
                (attachment_id,),
            ).fetchone()

    def set_attachment_email(
        self, attachment_id: int, include_in_email: bool
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self.session() as connection:
            attachment = connection.execute(
                "SELECT order_id FROM order_attachments WHERE id = ?",
                (attachment_id,),
            ).fetchone()
            connection.execute(
                """
                UPDATE order_attachments
                SET include_in_email = ?
                WHERE id = ?
                """,
                (int(include_in_email), attachment_id),
            )
            if attachment is not None:
                self._touch_order(connection, attachment["order_id"], now)
                self._record_order_audit(
                    connection,
                    attachment["order_id"],
                    (
                        "Document inclus dans l'e-mail"
                        if include_in_email
                        else "Document exclu de l'e-mail"
                    ),
                    occurred_at=now,
                )

    def delete_order_attachment(self, attachment_id: int) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self.session() as connection:
            attachment = connection.execute(
                """
                SELECT order_id, display_name FROM order_attachments
                WHERE id = ?
                """,
                (attachment_id,),
            ).fetchone()
            connection.execute(
                "DELETE FROM order_attachments WHERE id = ?",
                (attachment_id,),
            )
            if attachment is not None:
                self._touch_order(connection, attachment["order_id"], now)
                self._record_order_audit(
                    connection,
                    attachment["order_id"],
                    f"Document supprimé : {attachment['display_name']}",
                    occurred_at=now,
                )

    def export_team_state(self) -> dict[str, object]:
        settings = self.get_settings()
        with self.connect() as connection:
            suppliers = {
                row["name"]: dict(row)
                for row in connection.execute(
                    """
                    SELECT name, cahpp_id, customer_number, contact_name, email,
                           phone, address, website, franco_ht,
                           minimum_order_ht, notes, updated_at, updated_by
                    FROM suppliers
                    ORDER BY name
                    """
                )
            }
            preferences = {
                row["code_cahpp"]: dict(row)
                for row in connection.execute(
                    """
                    SELECT code_cahpp, favorite, usual_cartons, short_name,
                           updated_at, updated_by
                    FROM product_team_state
                    """
                )
            }
            overrides = {
                row["code_cahpp"]: dict(row)
                for row in connection.execute(
                    """
                    SELECT p.code_cahpp, po.supplier_ref, po.designation,
                           po.conditionnement, po.unit_packaging,
                           po.unit_price, po.vat, po.updated_at, po.updated_by
                    FROM product_overrides po
                    JOIN products p ON p.id = po.product_id
                    WHERE p.source = 'CAHPP'
                    """
                )
            }
            manual_products = {
                row["code_cahpp"]: dict(row)
                for row in connection.execute(
                    """
                    SELECT p.code_cahpp, p.supplier_name, p.supplier_ref,
                           p.designation, p.conditionnement, p.qml, p.vat,
                           p.unit_price, p.unit_packaging, p.active,
                           p.favorite, p.usual_cartons, p.short_name,
                           p.created_at, p.updated_at, p.created_by, p.updated_by
                    FROM products p
                    WHERE p.source = 'LOCAL'
                    """
                )
            }
        return {
            "format": 1,
            "suppliers": suppliers,
            "preferences": preferences,
            "overrides": overrides,
            "manual_products": manual_products,
            "team_settings": {
                "updated_at": settings.get("team_settings_updated_at", ""),
                "updated_by": settings.get("team_settings_updated_by", ""),
                "values": {
                    key: settings.get(key, "") for key in TEAM_SETTING_KEYS
                },
            },
        }

    @staticmethod
    def _is_remote_newer(
        remote: Mapping[str, object],
        local: Mapping[str, object] | sqlite3.Row | None,
    ) -> bool:
        if local is None:
            return True
        remote_key = (
            str(remote.get("updated_at") or ""),
            str(remote.get("updated_by") or ""),
        )
        local_key = (
            str(local["updated_at"] or ""),
            str(local["updated_by"] or ""),
        )
        return remote_key > local_key

    def apply_team_state(self, state: Mapping[str, object]) -> dict[str, int]:
        counts = {
            "suppliers": 0,
            "preferences": 0,
            "overrides": 0,
            "manual_products": 0,
            "settings": 0,
        }
        affected_products: set[int] = set()
        with self.session() as connection:
            for name, raw in dict(state.get("suppliers") or {}).items():
                record = dict(raw)
                local = connection.execute(
                    """
                    SELECT updated_at, updated_by FROM suppliers WHERE name = ?
                    """,
                    (name,),
                ).fetchone()
                if not self._is_remote_newer(record, local):
                    continue
                connection.execute(
                    """
                    INSERT INTO suppliers(
                        cahpp_id, name, customer_number, contact_name, email,
                        phone, address, website, franco_ht, minimum_order_ht,
                        notes, updated_at, updated_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        cahpp_id = COALESCE(excluded.cahpp_id, suppliers.cahpp_id),
                        customer_number = excluded.customer_number,
                        contact_name = excluded.contact_name,
                        email = excluded.email,
                        phone = excluded.phone,
                        address = excluded.address,
                        website = excluded.website,
                        franco_ht = excluded.franco_ht,
                        minimum_order_ht = excluded.minimum_order_ht,
                        notes = excluded.notes,
                        updated_at = excluded.updated_at,
                        updated_by = excluded.updated_by
                    """,
                    (
                        record.get("cahpp_id"),
                        name,
                        record.get("customer_number") or "",
                        record.get("contact_name") or "",
                        record.get("email") or "",
                        record.get("phone") or "",
                        record.get("address") or "",
                        record.get("website") or "",
                        record.get("franco_ht"),
                        record.get("minimum_order_ht"),
                        record.get("notes") or "",
                        record.get("updated_at") or "",
                        record.get("updated_by") or "",
                    ),
                )
                counts["suppliers"] += 1

            for code, raw in dict(state.get("manual_products") or {}).items():
                record = dict(raw)
                local = connection.execute(
                    """
                    SELECT id, updated_at, updated_by
                    FROM products WHERE code_cahpp = ?
                    """,
                    (code,),
                ).fetchone()
                if not self._is_remote_newer(record, local):
                    continue
                supplier_name = str(record.get("supplier_name") or "").strip()
                supplier = connection.execute(
                    "SELECT id FROM suppliers WHERE name = ?", (supplier_name,)
                ).fetchone()
                if supplier is None:
                    cursor = connection.execute(
                        """
                        INSERT INTO suppliers(name, updated_at, updated_by)
                        VALUES (?, ?, ?)
                        """,
                        (
                            supplier_name or "Fournisseur non renseigné",
                            record.get("updated_at") or "",
                            record.get("updated_by") or "",
                        ),
                    )
                    supplier_id = int(cursor.lastrowid)
                else:
                    supplier_id = int(supplier["id"])
                connection.execute(
                    """
                    INSERT INTO products(
                        code_cahpp, supplier_id, supplier_name, supplier_ref,
                        designation, conditionnement, qml, vat, unit_price,
                        unit_packaging, active, source, favorite,
                        usual_cartons, short_name, created_by, updated_by,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'LOCAL', ?, ?, ?,
                              ?, ?, ?, ?)
                    ON CONFLICT(code_cahpp) DO UPDATE SET
                        supplier_id = excluded.supplier_id,
                        supplier_name = excluded.supplier_name,
                        supplier_ref = excluded.supplier_ref,
                        designation = excluded.designation,
                        conditionnement = excluded.conditionnement,
                        qml = excluded.qml,
                        vat = excluded.vat,
                        unit_price = excluded.unit_price,
                        unit_packaging = excluded.unit_packaging,
                        active = excluded.active,
                        favorite = excluded.favorite,
                        usual_cartons = excluded.usual_cartons,
                        short_name = excluded.short_name,
                        updated_by = excluded.updated_by,
                        updated_at = excluded.updated_at
                    """,
                    (
                        code,
                        supplier_id,
                        supplier_name,
                        record.get("supplier_ref") or "",
                        record.get("designation") or "",
                        record.get("conditionnement"),
                        record.get("qml"),
                        record.get("vat"),
                        record.get("unit_price"),
                        record.get("unit_packaging") or "",
                        int(bool(record.get("active", 1))),
                        int(bool(record.get("favorite", 0))),
                        record.get("usual_cartons") or 1,
                        record.get("short_name") or "",
                        record.get("created_by") or "",
                        record.get("updated_by") or "",
                        record.get("created_at")
                        or record.get("updated_at")
                        or datetime.now().isoformat(timespec="seconds"),
                        record.get("updated_at") or "",
                    ),
                )
                product = connection.execute(
                    "SELECT id FROM products WHERE code_cahpp = ?", (code,)
                ).fetchone()
                if product:
                    affected_products.add(int(product["id"]))
                counts["manual_products"] += 1

            for code, raw in dict(state.get("preferences") or {}).items():
                record = dict(raw)
                local = connection.execute(
                    """
                    SELECT updated_at, updated_by
                    FROM product_team_state WHERE code_cahpp = ?
                    """,
                    (code,),
                ).fetchone()
                if not self._is_remote_newer(record, local):
                    continue
                connection.execute(
                    """
                    INSERT INTO product_team_state(
                        code_cahpp, favorite, usual_cartons, short_name,
                        updated_at, updated_by
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(code_cahpp) DO UPDATE SET
                        favorite = excluded.favorite,
                        usual_cartons = excluded.usual_cartons,
                        short_name = excluded.short_name,
                        updated_at = excluded.updated_at,
                        updated_by = excluded.updated_by
                    """,
                    (
                        code,
                        int(bool(record.get("favorite", 0))),
                        record.get("usual_cartons") or 1,
                        record.get("short_name") or "",
                        record.get("updated_at") or "",
                        record.get("updated_by") or "",
                    ),
                )
                connection.execute(
                    """
                    UPDATE products
                    SET favorite = ?, usual_cartons = ?, short_name = ?
                    WHERE code_cahpp = ?
                    """,
                    (
                        int(bool(record.get("favorite", 0))),
                        record.get("usual_cartons") or 1,
                        record.get("short_name") or "",
                        code,
                    ),
                )
                counts["preferences"] += 1

            for code, raw in dict(state.get("overrides") or {}).items():
                record = dict(raw)
                product = connection.execute(
                    "SELECT id FROM products WHERE code_cahpp = ?", (code,)
                ).fetchone()
                if product is None:
                    continue
                product_id = int(product["id"])
                local = connection.execute(
                    """
                    SELECT updated_at, updated_by
                    FROM product_overrides WHERE product_id = ?
                    """,
                    (product_id,),
                ).fetchone()
                if not self._is_remote_newer(record, local):
                    continue
                connection.execute(
                    """
                    INSERT INTO product_overrides(
                        product_id, supplier_ref, designation, conditionnement,
                        unit_packaging, unit_price, vat, updated_at, updated_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(product_id) DO UPDATE SET
                        supplier_ref = excluded.supplier_ref,
                        designation = excluded.designation,
                        conditionnement = excluded.conditionnement,
                        unit_packaging = excluded.unit_packaging,
                        unit_price = excluded.unit_price,
                        vat = excluded.vat,
                        updated_at = excluded.updated_at,
                        updated_by = excluded.updated_by
                    """,
                    (
                        product_id,
                        record.get("supplier_ref"),
                        record.get("designation"),
                        record.get("conditionnement"),
                        record.get("unit_packaging"),
                        record.get("unit_price"),
                        record.get("vat"),
                        record.get("updated_at") or "",
                        record.get("updated_by") or "",
                    ),
                )
                affected_products.add(product_id)
                counts["overrides"] += 1

            team_settings = dict(state.get("team_settings") or {})
            local_stamp = connection.execute(
                """
                SELECT value FROM settings
                WHERE key = 'team_settings_updated_at'
                """
            ).fetchone()
            local_updated_at = local_stamp["value"] if local_stamp else ""
            if str(team_settings.get("updated_at") or "") > local_updated_at:
                values = dict(team_settings.get("values") or {})
                values["team_settings_updated_at"] = str(
                    team_settings.get("updated_at") or ""
                )
                values["team_settings_updated_by"] = str(
                    team_settings.get("updated_by") or ""
                )
                connection.executemany(
                    """
                    INSERT INTO settings(key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (
                        (key, str(value or "").strip())
                        for key, value in values.items()
                        if key in TEAM_SETTING_KEYS
                        or key
                        in {
                            "team_settings_updated_at",
                            "team_settings_updated_by",
                        }
                    ),
                )
                counts["settings"] = 1

            for product_id in affected_products:
                self._add_product_to_search(connection, product_id)
        return counts

    def export_order(self, order_id: int) -> dict[str, object]:
        order, lines = self.get_order(order_id)
        attachments = self.list_order_attachments(order_id)
        with self.connect() as connection:
            audits = list(
                connection.execute(
                    """
                    SELECT event_uid, action, actor_id, actor_name,
                           occurred_at, details
                    FROM order_audit
                    WHERE order_id = ?
                    ORDER BY occurred_at, id
                    """,
                    (order_id,),
                )
            )
        order_values = {
            key: order[key]
            for key in (
                "order_number",
                "order_date",
                "status",
                "notes",
                "total_ht",
                "total_vat",
                "total_ttc",
                "pdf_path",
                "email_prepared_at",
                "sent_at",
                "shared_uid",
                "shared_revision",
                "catalog_hash",
                "created_by",
                "updated_by",
                "sent_by",
                "created_at",
                "updated_at",
            )
        }
        return {
            "format": 1,
            "order": order_values,
            "supplier": {
                "name": order["supplier_name"],
                "customer_number": order["customer_number"] or "",
                "email": order["supplier_email"] or "",
                "phone": order["supplier_phone"] or "",
            },
            "lines": [
                {
                    key: line[key]
                    for key in (
                        "code_cahpp",
                        "supplier_ref",
                        "designation",
                        "cartons",
                        "units_per_carton",
                        "total_units",
                        "unit_price",
                        "vat",
                        "total_ht",
                        "line_order",
                    )
                }
                for line in lines
            ],
            "attachments": [
                {
                    key: attachment[key]
                    for key in (
                        "kind",
                        "display_name",
                        "stored_path",
                        "include_in_email",
                        "added_at",
                    )
                }
                for attachment in attachments
            ],
            "audit": [dict(row) for row in audits],
        }

    def import_order(self, payload: Mapping[str, object]) -> tuple[int, bool]:
        order = dict(payload.get("order") or {})
        supplier_payload = dict(payload.get("supplier") or {})
        shared_uid = str(order.get("shared_uid") or "").strip()
        order_number = str(order.get("order_number") or "").strip()
        if not shared_uid or not order_number:
            raise ValueError("Commande partagée incomplète.")
        now = datetime.now().isoformat(timespec="seconds")
        with self.session() as connection:
            existing = connection.execute(
                """
                SELECT * FROM orders
                WHERE shared_uid = ? OR order_number = ?
                ORDER BY shared_uid = ? DESC
                LIMIT 1
                """,
                (shared_uid, order_number, shared_uid),
            ).fetchone()
            remote_revision = int(order.get("shared_revision") or 0)
            if existing is not None:
                local_revision = int(existing["shared_revision"] or 0)
                if local_revision > remote_revision:
                    return int(existing["id"]), False
                if (
                    local_revision == remote_revision
                    and str(existing["updated_at"] or "")
                    >= str(order.get("updated_at") or "")
                    and existing["sync_state"] == "Synchronisée"
                ):
                    return int(existing["id"]), False

            supplier_name = str(supplier_payload.get("name") or "").strip()
            supplier = connection.execute(
                "SELECT id FROM suppliers WHERE name = ?", (supplier_name,)
            ).fetchone()
            if supplier is None:
                cursor = connection.execute(
                    """
                    INSERT INTO suppliers(
                        name, customer_number, email, phone, updated_at,
                        updated_by
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        supplier_name or "Fournisseur non renseigné",
                        supplier_payload.get("customer_number") or "",
                        supplier_payload.get("email") or "",
                        supplier_payload.get("phone") or "",
                        order.get("updated_at") or now,
                        order.get("updated_by") or "",
                    ),
                )
                supplier_id = int(cursor.lastrowid)
            else:
                supplier_id = int(supplier["id"])

            values = (
                order_number,
                supplier_id,
                order.get("order_date") or date.today().isoformat(),
                order.get("status") or "Brouillon",
                order.get("notes") or "",
                order.get("total_ht") or 0,
                order.get("total_vat") or 0,
                order.get("total_ttc") or 0,
                order.get("pdf_path") or "",
                order.get("email_prepared_at") or "",
                order.get("sent_at") or "",
                shared_uid,
                remote_revision,
                "Synchronisée",
                order.get("catalog_hash") or "",
                order.get("created_by") or "",
                order.get("updated_by") or "",
                order.get("sent_by") or "",
                now,
                order.get("created_at") or now,
                order.get("updated_at") or now,
            )
            if existing is None:
                cursor = connection.execute(
                    """
                    INSERT INTO orders(
                        order_number, supplier_id, order_date, status, notes,
                        total_ht, total_vat, total_ttc, pdf_path,
                        email_prepared_at, sent_at, shared_uid,
                        shared_revision, sync_state, catalog_hash,
                        created_by, updated_by, sent_by, last_synced_at,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                              ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                order_id = int(cursor.lastrowid)
            else:
                order_id = int(existing["id"])
                connection.execute(
                    """
                    UPDATE orders SET
                        order_number = ?, supplier_id = ?, order_date = ?,
                        status = ?, notes = ?, total_ht = ?, total_vat = ?,
                        total_ttc = ?, pdf_path = ?, email_prepared_at = ?,
                        sent_at = ?, shared_uid = ?, shared_revision = ?,
                        sync_state = ?, catalog_hash = ?, created_by = ?,
                        updated_by = ?, sent_by = ?, last_synced_at = ?,
                        created_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (*values, order_id),
                )
                connection.execute(
                    "DELETE FROM order_lines WHERE order_id = ?", (order_id,)
                )
                connection.execute(
                    "DELETE FROM order_attachments WHERE order_id = ?",
                    (order_id,),
                )

            for line in list(payload.get("lines") or []):
                item = dict(line)
                product = connection.execute(
                    "SELECT id FROM products WHERE code_cahpp = ?",
                    (item.get("code_cahpp") or "",),
                ).fetchone()
                connection.execute(
                    """
                    INSERT INTO order_lines(
                        order_id, product_id, code_cahpp, supplier_ref,
                        designation, cartons, units_per_carton, total_units,
                        unit_price, vat, total_ht, line_order
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        int(product["id"]) if product else None,
                        item.get("code_cahpp") or "",
                        item.get("supplier_ref") or "",
                        item.get("designation") or "",
                        item.get("cartons") or 0,
                        item.get("units_per_carton") or 0,
                        item.get("total_units") or 0,
                        item.get("unit_price") or 0,
                        item.get("vat") or 0,
                        item.get("total_ht") or 0,
                        item.get("line_order") or 0,
                    ),
                )
            for attachment in list(payload.get("attachments") or []):
                item = dict(attachment)
                connection.execute(
                    """
                    INSERT INTO order_attachments(
                        order_id, kind, display_name, stored_path,
                        include_in_email, added_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        item.get("kind") or "Pièce jointe",
                        item.get("display_name") or "",
                        item.get("stored_path") or "",
                        int(bool(item.get("include_in_email", 0))),
                        item.get("added_at") or now,
                    ),
                )
            for audit in list(payload.get("audit") or []):
                item = dict(audit)
                self._record_order_audit(
                    connection,
                    order_id,
                    str(item.get("action") or ""),
                    str(item.get("details") or ""),
                    str(item.get("occurred_at") or now),
                    str(item.get("event_uid") or uuid.uuid4()),
                    str(item.get("actor_id") or ""),
                    str(item.get("actor_name") or ""),
                )
        return order_id, True

    def pending_order_ids(self) -> list[int]:
        with self.connect() as connection:
            return [
                int(row["id"])
                for row in connection.execute(
                    """
                    SELECT id FROM orders
                    WHERE sync_state <> 'Synchronisée'
                    ORDER BY id
                    """
                )
            ]

    def all_order_ids(self) -> list[int]:
        with self.connect() as connection:
            return [
                int(row["id"])
                for row in connection.execute(
                    "SELECT id FROM orders ORDER BY id"
                )
            ]

    def mark_order_synced(self, order_id: int) -> None:
        with self.session() as connection:
            connection.execute(
                """
                UPDATE orders
                SET sync_state = 'Synchronisée', last_synced_at = ?
                WHERE id = ?
                """,
                (datetime.now().isoformat(timespec="seconds"), order_id),
            )

    def update_order_shared_paths(
        self,
        order_id: int,
        pdf_path: str | None = None,
        attachment_paths: Mapping[str, str] | None = None,
    ) -> None:
        with self.session() as connection:
            if pdf_path is not None:
                connection.execute(
                    "UPDATE orders SET pdf_path = ? WHERE id = ?",
                    (pdf_path, order_id),
                )
            for display_name, stored_path in (attachment_paths or {}).items():
                connection.execute(
                    """
                    UPDATE order_attachments SET stored_path = ?
                    WHERE order_id = ? AND display_name = ?
                    """,
                    (stored_path, order_id, display_name),
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

    def ordered_changes_for_import(self, import_id: int) -> list[sqlite3.Row]:
        """Retourne les changements de prix/conditionnement d'articles commandés."""
        with self.connect() as connection:
            return list(
                connection.execute(
                    """
                    WITH changes AS (
                        SELECT
                            ph.product_id,
                            ph.import_id,
                            ph.unit_price AS new_price,
                            ph.conditionnement AS new_pack,
                            COALESCE(
                                (
                                    SELECT ph2.unit_price
                                    FROM price_history ph2
                                    WHERE ph2.product_id = ph.product_id
                                      AND ph2.import_id < ph.import_id
                                    ORDER BY ph2.import_id DESC
                                    LIMIT 1
                                ),
                                (
                                    SELECT ol.unit_price
                                    FROM order_lines ol
                                    JOIN orders o ON o.id = ol.order_id
                                    WHERE ol.product_id = ph.product_id
                                    ORDER BY o.order_date DESC, o.id DESC
                                    LIMIT 1
                                )
                            ) AS old_price,
                            COALESCE(
                                (
                                    SELECT ph2.conditionnement
                                    FROM price_history ph2
                                    WHERE ph2.product_id = ph.product_id
                                      AND ph2.import_id < ph.import_id
                                    ORDER BY ph2.import_id DESC
                                    LIMIT 1
                                ),
                                (
                                    SELECT ol.units_per_carton
                                    FROM order_lines ol
                                    JOIN orders o ON o.id = ol.order_id
                                    WHERE ol.product_id = ph.product_id
                                    ORDER BY o.order_date DESC, o.id DESC
                                    LIMIT 1
                                )
                            ) AS old_pack
                        FROM price_history ph
                        WHERE ph.import_id = ?
                    )
                    SELECT p.id AS product_id, p.code_cahpp, p.supplier_name,
                           p.supplier_ref, p.designation, p.active,
                           c.old_price, c.new_price, c.old_pack, c.new_pack
                    FROM changes c
                    JOIN products p ON p.id = c.product_id
                    WHERE EXISTS (
                        SELECT 1 FROM order_lines ol
                        WHERE ol.product_id = c.product_id
                    )
                      AND (
                          c.old_price IS NOT c.new_price
                          OR c.old_pack IS NOT c.new_pack
                      )
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
                SELECT p.id, p.code_cahpp,
                       COALESCE(po.supplier_ref, p.supplier_ref),
                       COALESCE(po.designation, p.designation),
                       p.supplier_name
                FROM products p
                LEFT JOIN product_overrides po ON po.product_id = p.id
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
