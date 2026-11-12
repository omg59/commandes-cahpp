from __future__ import annotations

import re
import logging
import sqlite3
import threading
import time
import uuid
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence
from .app_logging import log_failure
from .numbers import parse_decimal

logger = logging.getLogger(__name__)


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
    internal_notes TEXT NOT NULL DEFAULT '',
    replacement_code_cahpp TEXT NOT NULL DEFAULT '',
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
    internal_notes TEXT NOT NULL DEFAULT '',
    replacement_code_cahpp TEXT NOT NULL DEFAULT '',
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
    requester_service TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Brouillon',
    notes TEXT NOT NULL DEFAULT '',
    total_ht REAL NOT NULL DEFAULT 0,
    total_vat REAL NOT NULL DEFAULT 0,
    total_ttc REAL NOT NULL DEFAULT 0,
    pdf_path TEXT NOT NULL DEFAULT '',
    email_prepared_at TEXT NOT NULL DEFAULT '',
    sent_at TEXT NOT NULL DEFAULT '',
    confirmed_at TEXT NOT NULL DEFAULT '',
    confirmed_by TEXT NOT NULL DEFAULT '',
    delivery_status TEXT NOT NULL DEFAULT 'Non suivie',
    delivered_at TEXT NOT NULL DEFAULT '',
    delivered_by TEXT NOT NULL DEFAULT '',
    invoiced_at TEXT NOT NULL DEFAULT '',
    invoiced_by TEXT NOT NULL DEFAULT '',
    expected_delivery_date TEXT NOT NULL DEFAULT '',
    archived_at TEXT NOT NULL DEFAULT '',
    archived_by TEXT NOT NULL DEFAULT '',
    shared_uid TEXT NOT NULL DEFAULT '',
    shared_revision INTEGER NOT NULL DEFAULT 0,
    sync_state TEXT NOT NULL DEFAULT 'Local',
    catalog_hash TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    updated_by TEXT NOT NULL DEFAULT '',
    sent_by TEXT NOT NULL DEFAULT '',
    deleted_at TEXT NOT NULL DEFAULT '',
    deleted_by TEXT NOT NULL DEFAULT '',
    last_synced_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(order_date DESC);

CREATE TABLE IF NOT EXISTS order_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    line_uid TEXT NOT NULL DEFAULT '',
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

CREATE INDEX IF NOT EXISTS idx_order_lines_order
ON order_lines(order_id, line_order);

CREATE TABLE IF NOT EXISTS order_receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    receipt_uid TEXT NOT NULL UNIQUE,
    receipt_date TEXT NOT NULL,
    reference TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    received_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_order_receipts_order
ON order_receipts(order_id, receipt_date, id);

CREATE TABLE IF NOT EXISTS receipt_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id INTEGER NOT NULL REFERENCES order_receipts(id) ON DELETE CASCADE,
    order_line_uid TEXT NOT NULL,
    quantity_received REAL NOT NULL DEFAULT 0,
    UNIQUE(receipt_id, order_line_uid)
);

CREATE INDEX IF NOT EXISTS idx_receipt_lines_uid
ON receipt_lines(order_line_uid);

CREATE TABLE IF NOT EXISTS order_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    comment_uid TEXT NOT NULL UNIQUE,
    body TEXT NOT NULL,
    author_name TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_order_comments_order
ON order_comments(order_id, created_at, id);

CREATE TABLE IF NOT EXISTS saved_order_filters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    query TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    delivery_status TEXT NOT NULL DEFAULT '',
    include_archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
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
    "sync_interval_seconds": "60",
    "pause_sync_while_editing": "1",
    "backup_reminder_days": "14",
    "last_backup_at": "",
    "last_backup_path": "",
    "integrity_check_days": "7",
    "last_integrity_check_at": "",
    "last_integrity_check_result": "",
    "automatic_archive_enabled": "0",
    "archive_after_months": "24",
    "last_maintenance_at": "",
    "dismissed_installer_version": "",
    "confirmation_reminder_days": "5",
    "delivery_reminder_days": "14",
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
    po.vat AS override_vat,
    po.validated_catalog_token AS override_validated_catalog_token
"""

CATALOG_REVIEW_SQL = """(
    (p.catalog_review_token <> '' AND p.catalog_review_token <> COALESCE(po.validated_catalog_token,''))
    OR (p.source='CAHPP' AND COALESCE(NULLIF(COALESCE(po.conditionnement,p.conditionnement),0),p.qml,0)<=0)
)"""


_SIMPLE_EMAIL_PATTERN = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


def repair_supplier_contact_value(field: str, value: object) -> str:
    """Répare uniquement les virgules manifestement issues du bug fournisseur."""
    text = str(value or "")
    if "," not in text:
        return text

    def repair_email_token(match: re.Match[str]) -> str:
        token = match.group(0)
        candidate = token.replace(",", ".")
        return candidate if _SIMPLE_EMAIL_PATTERN.fullmatch(candidate) else token

    if field == "email":
        candidate = text.replace(",", ".")
        if _SIMPLE_EMAIL_PATTERN.fullmatch(candidate):
            return candidate
        return text
    if field == "website":
        if not re.search(r"\s", text):
            return text.replace(",", ".")
        return re.sub(
            r"(?:https?://|www\.)?[^\s,]+(?:,[^\s,]+)+",
            lambda match: match.group(0).replace(",", "."),
            text,
            flags=re.IGNORECASE,
        )
    if field == "phone":
        if re.fullmatch(r"[\d\s+().,/-]+", text):
            return re.sub(r"(?<=\d),(?=\d)", ".", text)
        return text
    if field == "contact_name":
        repaired = re.sub(r"\S+@\S+", repair_email_token, text)
        repaired = re.sub(
            r"(?:\d{1,3},){2,}\d{1,3}",
            lambda match: match.group(0).replace(",", "."),
            repaired,
        )
        repaired = re.sub(
            r"www(?:,[^\s,]+)+",
            lambda match: match.group(0).replace(",", "."),
            repaired,
            flags=re.IGNORECASE,
        )
        return repaired
    return text


def money(value: Decimal | float | int | str | None) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return parse_decimal(value).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


class SearchCancelled(Exception):
    """La recherche a été remplacée par une saisie plus récente."""


class SearchTimeoutError(Exception):
    """La recherche dégradée a dépassé le temps maximal autorisé."""


class SearchIndexError(Exception):
    """L'index plein texte n'est pas utilisable en toute sécurité."""


@dataclass(frozen=True)
class ProductSearchResult:
    rows: list[dict[str, object]]
    mode: str
    elapsed_ms: int
    repaired: bool = False
    warning: str = ""


class ManagedConnection(sqlite3.Connection):
    """Valide/annule la transaction puis ferme la connexion à la sortie du with.

    Le context manager sqlite3 standard ne ferme pas la connexion. L'application
    ouvre une connexion par opération ; sa durée de vie doit rester bornée,
    notamment pour libérer les handles et journaux WAL sous Windows.
    """

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fts_available = True
        self.fts_error = ""
        self._fts_verified = False
        self._fts_status_cache: dict[str, object] = {}
        self._fts_lock = threading.RLock()
        self._fts_retry_after = 0.0
        self.last_search_repair: dict[str, object] = {}
        self._search_stats_prepared = False
        self._search_stats_retry_after = 0.0
        self.search_plan_preparation: dict[str, object] = {}
        self.current_user_id = ""
        self.current_user_name = "Utilisateur"
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, factory=ManagedConnection)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 30000")
        except Exception:
            connection.close()
            raise
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
        with self.connect() as bootstrap:
            bootstrap.execute("PRAGMA busy_timeout = 30000")
            bootstrap.execute("PRAGMA journal_mode = WAL")
        with self.session() as connection:
            connection.executescript(SCHEMA)
            self._migrate_schema(connection)
            try:
                self._create_search_table(connection)
            except sqlite3.DatabaseError as exc:
                log_failure(logger, "fts_initialisation_echec", exc)
                self.fts_available = False
                self.fts_error = f"{type(exc).__name__}: {exc}"
            connection.executemany(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                DEFAULT_SETTINGS.items(),
            )
            connection.execute("PRAGMA user_version = 16")

    def _create_search_table(self, connection: sqlite3.Connection) -> None:
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
        self.fts_available = True
        self.fts_error = ""

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
        self._ensure_column(
            connection, "orders", "sync_base_revision", "INTEGER NOT NULL DEFAULT 0"
        )
        previous_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        for column, declaration in (
            ("contact_name", "TEXT NOT NULL DEFAULT ''"),
            ("address", "TEXT NOT NULL DEFAULT ''"),
            ("website", "TEXT NOT NULL DEFAULT ''"),
            ("minimum_order_ht", "REAL"),
            ("updated_by", "TEXT NOT NULL DEFAULT ''"),
        ):
            self._ensure_column(connection, "suppliers", column, declaration)
        if previous_version < 14:
            self._repair_supplier_contact_punctuation(connection)
        for column, declaration in (
            ("email_prepared_at", "TEXT NOT NULL DEFAULT ''"),
            ("sent_at", "TEXT NOT NULL DEFAULT ''"),
            ("requester_service", "TEXT NOT NULL DEFAULT ''"),
            ("confirmed_at", "TEXT NOT NULL DEFAULT ''"),
            ("confirmed_by", "TEXT NOT NULL DEFAULT ''"),
            ("delivery_status", "TEXT NOT NULL DEFAULT 'Non suivie'"),
            ("delivered_at", "TEXT NOT NULL DEFAULT ''"),
            ("delivered_by", "TEXT NOT NULL DEFAULT ''"),
            ("invoiced_at", "TEXT NOT NULL DEFAULT ''"),
            ("invoiced_by", "TEXT NOT NULL DEFAULT ''"),
            ("expected_delivery_date", "TEXT NOT NULL DEFAULT ''"),
            ("archived_at", "TEXT NOT NULL DEFAULT ''"),
            ("archived_by", "TEXT NOT NULL DEFAULT ''"),
            ("shared_uid", "TEXT NOT NULL DEFAULT ''"),
            ("shared_revision", "INTEGER NOT NULL DEFAULT 0"),
            ("sync_state", "TEXT NOT NULL DEFAULT 'Local'"),
            ("catalog_hash", "TEXT NOT NULL DEFAULT ''"),
            ("created_by", "TEXT NOT NULL DEFAULT ''"),
            ("updated_by", "TEXT NOT NULL DEFAULT ''"),
            ("sent_by", "TEXT NOT NULL DEFAULT ''"),
            ("deleted_at", "TEXT NOT NULL DEFAULT ''"),
            ("deleted_by", "TEXT NOT NULL DEFAULT ''"),
            ("last_synced_at", "TEXT NOT NULL DEFAULT ''"),
        ):
            self._ensure_column(connection, "orders", column, declaration)
        self._ensure_column(
            connection,
            "order_lines",
            "line_uid",
            "TEXT NOT NULL DEFAULT ''",
        )
        for row in connection.execute("SELECT id FROM order_lines WHERE line_uid = ''"):
            connection.execute(
                "UPDATE order_lines SET line_uid = ? WHERE id = ?",
                (str(uuid.uuid4()), row["id"]),
            )
        if previous_version < 16:
            connection.execute(
                "UPDATE orders SET sync_base_revision=shared_revision WHERE sync_state='Synchronisée'"
            )
        for column, declaration in (
            ("created_by", "TEXT NOT NULL DEFAULT ''"),
            ("updated_by", "TEXT NOT NULL DEFAULT ''"),
            ("internal_notes", "TEXT NOT NULL DEFAULT ''"),
            ("replacement_code_cahpp", "TEXT NOT NULL DEFAULT ''"),
        ):
            self._ensure_column(connection, "products", column, declaration)
        for column in ("catalog_review_token", "catalog_review_reason"):
            self._ensure_column(
                connection, "products", column, "TEXT NOT NULL DEFAULT ''"
            )
        self._ensure_column(
            connection,
            "product_overrides",
            "validated_catalog_token",
            "TEXT NOT NULL DEFAULT ''",
        )
        for column, declaration in (
            ("mode", "TEXT NOT NULL DEFAULT 'full'"),
            ("period", "TEXT NOT NULL DEFAULT ''"),
            ("deactivated_count", "INTEGER NOT NULL DEFAULT 0"),
            ("review_count", "INTEGER NOT NULL DEFAULT 0"),
            ("warnings_json", "TEXT NOT NULL DEFAULT '[]'"),
            ("previous_catalog_hash", "TEXT NOT NULL DEFAULT ''"),
        ):
            self._ensure_column(connection, "imports", column, declaration)
        for column, declaration in (
            ("internal_notes", "TEXT NOT NULL DEFAULT ''"),
            ("replacement_code_cahpp", "TEXT NOT NULL DEFAULT ''"),
        ):
            self._ensure_column(connection, "product_team_state", column, declaration)
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
                internal_notes, replacement_code_cahpp, updated_at, updated_by
            )
            SELECT code_cahpp, favorite, usual_cartons, short_name,
                   internal_notes, replacement_code_cahpp, updated_at, updated_by
            FROM products
            WHERE favorite <> 0 OR usual_cartons <> 1 OR short_name <> ''
               OR internal_notes <> '' OR replacement_code_cahpp <> ''
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_shared_uid
            ON orders(shared_uid) WHERE shared_uid <> ''
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_orders_delivery
            ON orders(delivery_status, archived_at, order_date DESC)
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_order_lines_uid
            ON order_lines(line_uid) WHERE line_uid <> ''
            """
        )
        connection.execute(
            """
            UPDATE orders
            SET delivery_status = 'En attente'
            WHERE sent_at <> '' AND delivery_status = 'Non suivie'
            """
        )

    @staticmethod
    def _repair_supplier_contact_punctuation(
        connection: sqlite3.Connection,
    ) -> None:
        repaired_at = datetime.now().isoformat(timespec="microseconds")
        for row in connection.execute(
            """
            SELECT id, contact_name, email, phone, website
            FROM suppliers
            """
        ).fetchall():
            values = {
                field: repair_supplier_contact_value(field, row[field])
                for field in ("contact_name", "email", "phone", "website")
            }
            if all(values[field] == (row[field] or "") for field in values):
                continue
            connection.execute(
                """
                UPDATE suppliers
                SET contact_name = ?, email = ?, phone = ?, website = ?,
                    updated_at = ?, updated_by = ?
                WHERE id = ?
                """,
                (
                    values["contact_name"],
                    values["email"],
                    values["phone"],
                    values["website"],
                    repaired_at,
                    "Correctif 1.3.3",
                    row["id"],
                ),
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
                    """
                    SELECT COUNT(*) FROM orders
                    WHERE deleted_at = ''
                    """
                ).fetchone()[0],
                "pending_deliveries": connection.execute(
                    """
                    SELECT COUNT(*) FROM orders
                    WHERE deleted_at = '' AND archived_at = ''
                      AND sent_at <> ''
                      AND delivery_status IN ('En attente', 'Partiellement livrée')
                    """
                ).fetchone()[0],
            }
            latest = connection.execute(
                "SELECT filename, imported_at, row_count FROM imports ORDER BY id DESC LIMIT 1"
            ).fetchone()
            stats["latest_import"] = dict(latest) if latest else None
            stats["delivery_orders"] = list(
                connection.execute(
                    """
                    SELECT o.id, o.order_number, o.sent_at, o.order_date,
                           o.total_ht, s.name AS supplier_name,
                           o.delivery_status,
                           COALESCE(SUM(ol.total_units), 0) AS ordered_units,
                           COALESCE((
                               SELECT SUM(rl.quantity_received)
                               FROM receipt_lines rl
                               JOIN order_receipts r ON r.id = rl.receipt_id
                               WHERE r.order_id = o.id
                           ), 0) AS received_units,
                           CAST(julianday('now') - julianday(
                               COALESCE(NULLIF(o.sent_at, ''), o.order_date)
                           ) AS INTEGER) AS waiting_days
                    FROM orders o
                    JOIN suppliers s ON s.id = o.supplier_id
                    JOIN order_lines ol ON ol.order_id = o.id
                    WHERE o.deleted_at = '' AND o.archived_at = ''
                      AND o.sent_at <> ''
                      AND o.delivery_status IN ('En attente', 'Partiellement livrée')
                    GROUP BY o.id
                    ORDER BY COALESCE(NULLIF(o.sent_at, ''), o.order_date), o.id
                    LIMIT 12
                    """
                )
            )
            reminder_values = {
                row["key"]: row["value"]
                for row in connection.execute(
                    """
                    SELECT key, value FROM settings
                    WHERE key IN (
                        'confirmation_reminder_days', 'delivery_reminder_days'
                    )
                    """
                )
            }
            try:
                confirmation_days = int(
                    reminder_values.get("confirmation_reminder_days", "5")
                )
            except ValueError:
                confirmation_days = 5
            try:
                delivery_days = int(
                    reminder_values.get("delivery_reminder_days", "14")
                )
            except ValueError:
                delivery_days = 14
            stats["alerts"] = self.order_alerts(
                confirmation_days=confirmation_days,
                delivery_days=delivery_days,
                limit=20,
            )
            stats["alert_count"] = len(stats["alerts"])
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
                datetime.now().isoformat(timespec="microseconds"),
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
        contact_name = repair_supplier_contact_value(
            "contact_name", contact_name
        )
        email = repair_supplier_contact_value("email", email)
        phone = repair_supplier_contact_value("phone", phone)
        website = repair_supplier_contact_value("website", website)
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
                    datetime.now().isoformat(timespec="microseconds"),
                    actor_name,
                    supplier_id,
                ),
            )

    @staticmethod
    def _fts_query(query: str) -> str:
        terms = re.findall(r"[\w]+", query, flags=re.UNICODE)
        return " AND ".join(f'"{term}"*' for term in terms[:10])

    @staticmethod
    def _fts_search_sql(where: str) -> str:
        # Des statistiques périmées peuvent faire choisir une boucle sur tous
        # les produits, avec réouverture de FTS5 pour chacun. CROSS JOIN impose
        # de partir des correspondances MATCH, puis de lire chaque produit par ID.
        return f"""SELECT {PRODUCT_SELECT}
                FROM product_search
                CROSS JOIN products p ON p.id = product_search.rowid
                LEFT JOIN product_overrides po ON po.product_id = p.id
                WHERE product_search MATCH ? AND {where}
                ORDER BY p.favorite DESC, bm25(product_search),
                         COALESCE(po.designation, p.designation)
                LIMIT ?"""

    @staticmethod
    def _execute_fts_search(connection, fts, where, parameters, limit):
        """Requête commune au contrôle fonctionnel et à la recherche utilisateur."""
        return list(connection.execute(
            Database._fts_search_sql(where), [fts, *parameters, limit],
        ))

    def _prepare_search_statistics(self) -> None:
        """Actualise les estimations du planificateur une fois par catalogue/session."""
        if self._search_stats_prepared or time.monotonic() < self._search_stats_retry_after:
            return
        started = time.perf_counter()
        status: dict[str, object] = {
            "checked_at": datetime.now().isoformat(timespec="seconds"), "success": False,
        }
        try:
            with self.connect() as connection:
                # Une analyse concurrente ne doit pas bloquer la recherche 30 s.
                connection.execute("PRAGMA busy_timeout = 1000")
                connection.execute("ANALYZE products")
                connection.execute("ANALYZE product_overrides")
            self._search_stats_prepared = True
            self._search_stats_retry_after = 0
            status["success"] = True
        except sqlite3.DatabaseError as exc:
            log_failure(logger, "recherche_statistiques_echec", exc)
            status["error_type"] = type(exc).__name__
            status["sqlite_code"] = getattr(exc, "sqlite_errorname", "")
            self._search_stats_retry_after = time.monotonic() + 30
        status["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
        self.search_plan_preparation = status
        logger.info("recherche_statistiques succes=%s duree_ms=%d", status["success"], status["elapsed_ms"])

    def prepare_catalog_statistics(self) -> None:
        """Rafraîchit les estimations avant une fusion de catalogue potentiellement massive."""
        with self._fts_lock:
            self._search_stats_prepared = False
            self._search_stats_retry_after = 0
            self._prepare_search_statistics()

    def catalog_search_plan(self) -> list[str]:
        """Expose le plan d'une recherche témoin, jamais le texte saisi par l'utilisateur."""
        try:
            with self.connect() as connection:
                return [str(row[3]) for row in connection.execute(
                    "EXPLAIN QUERY PLAN " + self._fts_search_sql("p.active = 1"),
                    ('"cahppdiagnostic"', 101),
                )]
        except sqlite3.DatabaseError as exc:
            return [f"Plan indisponible : {type(exc).__name__} / {getattr(exc, 'sqlite_errorname', '')}"]

    def _probe_search_index(self, connection) -> None:
        """Teste MATCH et le classement sur un article connu, sans exporter son texte."""
        samples = connection.execute(
            """SELECT p.id, p.code_cahpp, COALESCE(po.supplier_ref, p.supplier_ref),
                      COALESCE(po.designation, p.designation), p.supplier_name
               FROM products p LEFT JOIN product_overrides po ON po.product_id = p.id
               ORDER BY p.id LIMIT 20"""
        )
        for sample in samples:
            for value in tuple(sample)[1:]:
                terms = re.findall(r"[^\W_]+", str(value or ""), flags=re.UNICODE)
                if terms:
                    rows = self._execute_fts_search(
                        connection, self._fts_query(terms[0]), "p.id = ?", [sample[0]], 1,
                    )
                    if not rows:
                        raise SearchIndexError(
                            "Le test de recherche ne retrouve pas un article connu."
                        )
                    return
        # Même un catalogue vide doit permettre d'exécuter MATCH et bm25.
        self._execute_fts_search(connection, '"cahppindexprobe"', "1 = 1", [], 1)

    def _search_index_failure(self, error: Exception, stage: str) -> str:
        """Classe l'erreur sans journaliser de requête ni de données métier."""
        text = str(error).lower()
        code = getattr(error, "sqlite_errorname", "")
        if "no such module: fts5" in text:
            detail = "Le moteur SQLite de cette installation ne fournit pas FTS5."
        elif code in {"SQLITE_BUSY", "SQLITE_LOCKED"} or "locked" in text:
            detail = "La base est occupée par une autre opération. Réessayez dans quelques instants."
        elif "readonly" in text or "read-only" in text:
            detail = "La base locale n'est pas accessible en écriture."
        elif code == "SQLITE_FULL":
            detail = "L'espace disque disponible est insuffisant."
        elif "bm25" in text or "requested context" in text:
            detail = "SQLite ne parvient pas à exécuter le classement des résultats FTS5."
        elif isinstance(error, SearchIndexError):
            detail = "Le test de recherche ne retrouve pas un article connu."
        elif "malformed" in text or "corrupt" in text or "checksum" in text or code.startswith("SQLITE_CORRUPT"):
            detail = "Les structures de l'index de recherche sont endommagées."
        elif "invalid fts5 file format" in text:
            detail = "Le format de l'index FTS5 est incompatible avec cette installation."
        else:
            detail = "Le contrôle ou la reconstruction de l'index a échoué."
        self.fts_error = f"{stage} : {detail} ({type(error).__name__}, {code or 'sans code SQLite'})."
        log_failure(logger, "fts_operation_echec", error)
        return self.fts_error

    def search_index_status(self, *, deep: bool = False) -> dict[str, object]:
        with self._fts_lock:
            self._prepare_search_statistics()
            return self._search_index_status(deep=deep)

    def _search_index_status(self, *, deep: bool = False) -> dict[str, object]:
        """Vérifie les entrées, leur contenu et une vraie recherche avec classement."""
        status: dict[str, object] = {
            "available": self.fts_available,
            "consistent": False,
            "products": 0,
            "indexed": 0,
            "missing": 0,
            "orphaned": 0,
            "mismatched": 0,
            "functional": False,
            "error": self.fts_error,
        }
        try:
            with self.connect() as connection:
                status["products"] = int(
                    connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
                )
                status["indexed"] = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM product_search"
                    ).fetchone()[0]
                )
                status["missing"] = int(
                    connection.execute(
                        """
                        SELECT COUNT(*)
                        FROM products p
                        LEFT JOIN product_search ps ON ps.rowid = p.id
                        WHERE ps.rowid IS NULL
                        """
                    ).fetchone()[0]
                )
                status["orphaned"] = int(
                    connection.execute(
                        """
                        SELECT COUNT(*)
                        FROM product_search ps
                        LEFT JOIN products p ON p.id = ps.rowid
                        WHERE p.id IS NULL
                        """
                    ).fetchone()[0]
                )
                status["mismatched"] = int(connection.execute(
                    """SELECT COUNT(*) FROM products p
                       JOIN product_search ps ON ps.rowid = p.id
                       LEFT JOIN product_overrides po ON po.product_id = p.id
                       WHERE COALESCE(ps.code_cahpp, '') <> COALESCE(p.code_cahpp, '')
                          OR COALESCE(ps.supplier_ref, '') <> COALESCE(po.supplier_ref, p.supplier_ref, '')
                          OR COALESCE(ps.designation, '') <> COALESCE(po.designation, p.designation, '')
                          OR COALESCE(ps.supplier_name, '') <> COALESCE(p.supplier_name, '')"""
                ).fetchone()[0])
                self._probe_search_index(connection)
                if deep:
                    connection.execute(
                        "INSERT INTO product_search(product_search) VALUES('integrity-check')"
                    )
                    connection.rollback()
                status["functional"] = True
        except (sqlite3.DatabaseError, SearchIndexError) as exc:
            self.fts_available = False
            self._fts_verified = False
            self._search_index_failure(exc, "Contrôle de recherche")
            status["available"] = False
            status["error"] = self.fts_error
            return status
        status["consistent"] = (
            int(status["products"]) == int(status["indexed"])
            and int(status["missing"]) == 0
            and int(status["orphaned"]) == 0
            and int(status["mismatched"]) == 0
            and bool(status["functional"])
        )
        self.fts_available = True
        status["available"] = True
        if not status["consistent"]:
            self._fts_verified = False
        status["error"] = "" if status["consistent"] else "Les entrées de l'index ne correspondent pas au catalogue local."
        self.fts_error = str(status["error"])
        return status

    def ensure_search_index(self, force: bool = False) -> dict[str, object]:
        """Vérifie puis répare l'index une seule fois par session si nécessaire."""
        with self._fts_lock:
            self._prepare_search_statistics()
            if self._fts_verified and not force:
                return dict(self._fts_status_cache)
            if not force and time.monotonic() < self._fts_retry_after:
                return dict(self._fts_status_cache)
            status = self.search_index_status(deep=True)
            repaired = False
            if not bool(status.get("consistent")):
                logger.warning("fts_reconstruction_necessaire")
                repaired = self.rebuild_search()
                status = self.search_index_status(deep=True)
                logger.info("fts_reconstruction terminee=%s", status.get("consistent"))
            status["repaired"] = repaired and bool(status.get("consistent"))
            self._fts_verified = bool(status.get("consistent"))
            self._fts_status_cache = dict(status)
            if not self._fts_verified:
                self._fts_retry_after = time.monotonic() + 30
            return dict(status)

    @staticmethod
    def _raise_interrupted_search(reason: dict[str, str]) -> None:
        if reason.get("value") == "cancelled":
            raise SearchCancelled()
        if reason.get("value") == "timeout":
            raise SearchTimeoutError(
                "La recherche a été interrompue pour préserver "
                "la réactivité de l'application."
            )

    def search_products_detailed(
        self,
        query: str = "",
        supplier_id: int | None = None,
        favorite_only: bool = False,
        limit: int = 200,
        include_inactive: bool = False,
        *,
        review_only: bool = False,
        allow_slow_fallback: bool = False,
        cancel_event: threading.Event | None = None,
        timeout_seconds: float = 4.0,
    ) -> ProductSearchResult:
        started = time.perf_counter()
        filters = []
        parameters: list[object] = []
        if not include_inactive:
            filters.append("p.active = 1")
        if supplier_id:
            filters.append("p.supplier_id = ?")
            parameters.append(supplier_id)
        if favorite_only:
            filters.append("p.favorite = 1")
        if review_only:
            filters.append(CATALOG_REVIEW_SQL)
        where = " AND ".join(filters) if filters else "1 = 1"
        query = query.strip()
        index_status: dict[str, object] = {}
        if query:
            index_status = self.ensure_search_index()

        deadline = time.perf_counter() + max(0.25, timeout_seconds)
        interruption = {"value": ""}

        def progress() -> int:
            if cancel_event is not None and cancel_event.is_set():
                interruption["value"] = "cancelled"
                return 1
            if time.perf_counter() >= deadline:
                interruption["value"] = "timeout"
                return 1
            return 0

        warning = ""
        repaired = bool(index_status.get("repaired"))
        with self.connect() as connection:
            connection.set_progress_handler(progress, 1000)
            if query and self.fts_available and bool(index_status.get("consistent")):
                fts = self._fts_query(query)
                if fts:
                    try:
                        rows = self._execute_fts_search(connection, fts, where, parameters, limit)
                        result = [self._effective_product(row) for row in rows]
                        return ProductSearchResult(
                            result,
                            "fts5",
                            round((time.perf_counter() - started) * 1000),
                            repaired=repaired,
                        )
                    except sqlite3.OperationalError as exc:
                        if "interrupt" in str(exc).lower():
                            self._raise_interrupted_search(interruption)
                        self.fts_available = False
                        self._fts_verified = False
                        self._search_index_failure(exc, "Recherche")
                        warning = "Index FTS5 indisponible : " + self.fts_error
                    except sqlite3.DatabaseError as exc:
                        self.fts_available = False
                        self._fts_verified = False
                        self._search_index_failure(exc, "Recherche")
                        warning = "Index FTS5 indisponible : " + self.fts_error

            if query and not allow_slow_fallback:
                raise SearchIndexError(
                    self.fts_error
                    or "L'index de recherche doit être réparé avant de continuer."
                )

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
            try:
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
                result = [self._effective_product(row) for row in rows]
            except sqlite3.OperationalError as exc:
                if "interrupt" in str(exc).lower():
                    self._raise_interrupted_search(interruption)
                raise
            return ProductSearchResult(
                result,
                "like" if query else "listing",
                round((time.perf_counter() - started) * 1000),
                repaired=repaired,
                warning=warning,
            )

    def search_products(
        self,
        query: str = "",
        supplier_id: int | None = None,
        favorite_only: bool = False,
        limit: int = 200,
        include_inactive: bool = False,
    ) -> list[dict[str, object]]:
        return self.search_products_detailed(
            query=query,
            supplier_id=supplier_id,
            favorite_only=favorite_only,
            limit=limit,
            include_inactive=include_inactive,
            allow_slow_fallback=True,
        ).rows

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
        product["has_override"] = has_override or bool(product.get("override_validated_catalog_token"))
        product["catalog_review_required"] = bool(
            product.get("catalog_review_token") and
            product["catalog_review_token"] != product.get("override_validated_catalog_token")
        ) or (product["source"] == "CAHPP" and money(product.get("conditionnement") or product.get("qml")) <= 0)
        if product["catalog_review_required"] and not product["catalog_review_reason"]:
            product["catalog_review_reason"] = "Conditionnement absent : quantité à renseigner."
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

    def update_product_team_details(
        self,
        product_id: int,
        internal_notes: str = "",
        replacement_code_cahpp: str = "",
    ) -> None:
        _, actor_name = self._actor()
        updated_at = datetime.now().isoformat(timespec="seconds")
        with self.session() as connection:
            product = connection.execute(
                """
                SELECT code_cahpp, favorite, usual_cartons, short_name
                FROM products WHERE id = ?
                """,
                (product_id,),
            ).fetchone()
            if product is None:
                raise ValueError("Article introuvable.")
            replacement = replacement_code_cahpp.strip()
            if replacement:
                replacement_row = connection.execute(
                    "SELECT id FROM products WHERE code_cahpp = ? AND active = 1",
                    (replacement,),
                ).fetchone()
                if replacement_row is None:
                    raise ValueError("La référence de remplacement est introuvable.")
                if int(replacement_row["id"]) == product_id:
                    raise ValueError("Un article ne peut pas se remplacer lui-même.")
            connection.execute(
                """
                UPDATE products
                SET internal_notes = ?, replacement_code_cahpp = ?,
                    updated_at = ?, updated_by = ?
                WHERE id = ?
                """,
                (
                    internal_notes.strip(),
                    replacement,
                    updated_at,
                    actor_name,
                    product_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO product_team_state(
                    code_cahpp, favorite, usual_cartons, short_name,
                    internal_notes, replacement_code_cahpp,
                    updated_at, updated_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code_cahpp) DO UPDATE SET
                    favorite = excluded.favorite,
                    usual_cartons = excluded.usual_cartons,
                    short_name = excluded.short_name,
                    internal_notes = excluded.internal_notes,
                    replacement_code_cahpp = excluded.replacement_code_cahpp,
                    updated_at = excluded.updated_at,
                    updated_by = excluded.updated_by
                """,
                (
                    product["code_cahpp"],
                    product["favorite"],
                    product["usual_cartons"],
                    product["short_name"],
                    internal_notes.strip(),
                    replacement,
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
        catalog_review_confirmed: bool = False,
        reviewed_catalog_token: str = "",
    ) -> None:
        product = self.get_product(product_id)
        if product is None or product["source"] != "CAHPP":
            raise ValueError("Cette référence n'est pas issue du catalogue CAHPP.")
        if product["catalog_review_required"] and (not catalog_review_confirmed or reviewed_catalog_token != product["catalog_review_token"]):
            raise ValueError("Confirmez la vérification des informations de cet article.")
        if parse_decimal(conditionnement, "Conditionnement", minimum=0) <= 0:
            raise ValueError("Le conditionnement doit être supérieur à zéro.")
        parse_decimal(unit_price, "Prix", minimum=0)
        parse_decimal(vat, "TVA", minimum=0, maximum=100)

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
                same = catalog_value is not None and money(value) == money(catalog_value)
            else:
                same = str(value or "").strip() == str(
                    catalog_value or ""
                ).strip()
            overrides[field] = None if same else value

        now = datetime.now().isoformat(timespec="microseconds")
        _, actor_name = self._actor()
        with self.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute("SELECT catalog_review_token FROM products WHERE id=?", (product_id,)).fetchone()
            if current is None or current[0] != product["catalog_review_token"]:
                raise ValueError("Le catalogue a changé pendant la modification. Rouvrez la fiche avant de confirmer.")
            connection.execute(
                """
                INSERT INTO product_overrides(
                    product_id, supplier_ref, designation, conditionnement,
                    unit_packaging, unit_price, vat, updated_at, updated_by, validated_catalog_token
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(product_id) DO UPDATE SET
                    supplier_ref = excluded.supplier_ref,
                    designation = excluded.designation,
                    conditionnement = excluded.conditionnement,
                    unit_packaging = excluded.unit_packaging,
                    unit_price = excluded.unit_price,
                    vat = excluded.vat,
                    updated_at = excluded.updated_at,
                    updated_by = excluded.updated_by,
                    validated_catalog_token = excluded.validated_catalog_token
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
                    product["catalog_review_token"] if catalog_review_confirmed else (product.get("override_validated_catalog_token") or ""),
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
        now = datetime.now().isoformat(timespec="microseconds")
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
                    validated_catalog_token = '',
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

    def _add_product_to_search(
        self, connection: sqlite3.Connection, product_id: int
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
        except sqlite3.OperationalError as exc:
            self._fts_verified = False
            log_failure(logger, "fts_article_indexation_echec", exc)

    def _remove_product_from_search(
        self, connection: sqlite3.Connection, product_id: int
    ) -> None:
        try:
            connection.execute(
                "DELETE FROM product_search WHERE rowid = ?", (product_id,)
            )
        except sqlite3.OperationalError as exc:
            self._fts_verified = False
            log_failure(logger, "fts_article_retrait_echec", exc)

    def validate_catalog_lines(self, lines, *, connection=None) -> None:
        """Refuse un article retiré, non vérifié ou un ancien colisage devenu caduc."""
        if connection is None:
            with self.connect() as owned:
                self.validate_catalog_lines(lines, connection=owned)
            return
        for line in lines:
            if not line.get("product_id"):
                continue
            row = connection.execute(
                f"SELECT {PRODUCT_SELECT} FROM products p LEFT JOIN product_overrides po ON po.product_id=p.id WHERE p.id=?",
                (line["product_id"],),
            ).fetchone()
            if row is None:
                continue
            product = self._effective_product(row)
            if not product["active"]:
                raise ValueError(f"L'article {product['supplier_ref']} n'est plus actif. Retirez-le de la préparation.")
            if product["catalog_review_required"]:
                raise ValueError(f"Vérifiez d'abord les informations de {product['supplier_ref']} dans Catalogue > Modifier l'article.")
            if product["catalog_review_token"]:
                quantities = [money(product[key]) for key in ("conditionnement", "qml") if product.get(key)]
                if money(line.get("units_per_carton")) not in quantities:
                    raise ValueError(f"Le conditionnement de {product['supplier_ref']} a changé. Retirez puis ajoutez de nouveau cette ligne.")

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
        requester_service: str = "",
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
            if cartons <= 0 or units_per_carton <= 0:
                raise ValueError("Les quantités et conditionnements doivent être positifs.")
            if unit_price < 0 or not 0 <= vat <= 100:
                raise ValueError("Prix négatif ou TVA hors limites (0 à 100 %).")
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
                    str(line.get("line_uid") or uuid.uuid4()),
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
            connection.execute("BEGIN IMMEDIATE")
            self.validate_catalog_lines(lines, connection=connection)
            if not is_new:
                existing = connection.execute(
                    "SELECT * FROM orders WHERE id = ?", (order_id,)
                ).fetchone()
                if (existing is None or not self.can_delete_unsent_order(existing)
                        or existing["status"] != "Brouillon"):
                    raise ValueError(
                        "Seul un brouillon non envoyé peut être modifié. "
                        "Reprenez d'abord la commande depuis l'historique."
                    )
            if is_new:
                order_number = order_number or self._next_order_number(
                    connection, selected_date
                )
                shared_uid = shared_uid or str(uuid.uuid4())
                cursor = connection.execute(
                    """
                    INSERT INTO orders(
                        order_number, supplier_id, order_date, requester_service,
                        status, notes,
                        total_ht, total_vat, total_ttc, shared_uid,
                        shared_revision, sync_state, catalog_hash,
                        created_by, updated_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'À synchroniser',
                              ?, ?, ?, ?, ?)
                    """,
                    (
                        order_number,
                        supplier_id,
                        selected_date.isoformat(),
                        requester_service.strip(),
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
                    SET supplier_id = ?, order_date = ?, requester_service = ?,
                        status = ?, notes = ?,
                        total_ht = ?, total_vat = ?, total_ttc = ?,
                        shared_revision = shared_revision + 1,
                        sync_state = 'À synchroniser', catalog_hash = ?,
                        updated_at = ?, updated_by = ?
                    WHERE id = ?
                    """,
                    (
                        supplier_id,
                        selected_date.isoformat(),
                        requester_service.strip(),
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
                    order_id, line_uid, product_id, code_cahpp, supplier_ref, designation,
                    cartons, units_per_carton, total_units, unit_price, vat,
                    total_ht, line_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        delivery_status: str = "",
        include_archived: bool = False,
        limit: int = 500,
        group: str = "",
    ) -> list[sqlite3.Row]:
        filters = ["COALESCE(o.deleted_at, '') = ''"]
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
        if delivery_status:
            if delivery_status == "À recevoir":
                filters.append(
                    "o.delivery_status IN ('En attente', 'Partiellement livrée')"
                )
            else:
                filters.append("o.delivery_status = ?")
                parameters.append(delivery_status)
        if not include_archived:
            filters.append("COALESCE(o.archived_at, '') = ''")
        if group == "À préparer / envoyer":
            filters.append("o.sent_at = ''")
        elif group == "À recevoir":
            filters.append("o.sent_at <> '' AND o.delivery_status <> 'Livrée'")
        elif group == "Terminées":
            filters.append("o.delivery_status = 'Livrée'")
        where = " AND ".join(filters)
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

    def list_saved_order_filters(self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT * FROM saved_order_filters
                    ORDER BY name COLLATE NOCASE
                    """
                )
            )

    def save_order_filter(
        self,
        name: str,
        query: str,
        status: str,
        delivery_status: str,
        include_archived: bool,
    ) -> None:
        name = name.strip()
        if not name:
            raise ValueError("Le nom du filtre est obligatoire.")
        with self.session() as connection:
            connection.execute(
                """
                INSERT INTO saved_order_filters(
                    name, query, status, delivery_status,
                    include_archived, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    query = excluded.query,
                    status = excluded.status,
                    delivery_status = excluded.delivery_status,
                    include_archived = excluded.include_archived
                """,
                (
                    name,
                    query.strip(),
                    status,
                    delivery_status,
                    int(include_archived),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )

    def delete_order_filter(self, name: str) -> None:
        with self.session() as connection:
            connection.execute(
                "DELETE FROM saved_order_filters WHERE name = ?", (name.strip(),)
            )

    def order_alerts(
        self,
        reference_date: date | None = None,
        confirmation_days: int = 5,
        delivery_days: int = 14,
        limit: int = 100,
    ) -> list[sqlite3.Row]:
        reference_date = reference_date or date.today()
        with self.connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT * FROM (
                        SELECT o.id, o.order_number, s.name AS supplier_name,
                               'Confirmation attendue' AS alert_type,
                               CAST(julianday(?) - julianday(substr(o.sent_at, 1, 10))
                                    AS INTEGER) AS overdue_days,
                               o.sent_at AS reference_value,
                               o.delivery_status
                        FROM orders o
                        JOIN suppliers s ON s.id = o.supplier_id
                        WHERE o.deleted_at = '' AND o.archived_at = ''
                          AND o.sent_at <> '' AND o.confirmed_at = ''
                          AND o.delivery_status <> 'Livrée'
                          AND julianday(?) - julianday(substr(o.sent_at, 1, 10)) >= ?
                        UNION ALL
                        SELECT o.id, o.order_number, s.name AS supplier_name,
                               'Livraison en retard' AS alert_type,
                               CAST(
                                   CASE
                                     WHEN o.expected_delivery_date <> ''
                                     THEN julianday(?) - julianday(o.expected_delivery_date)
                                     ELSE julianday(?) - julianday(substr(o.sent_at, 1, 10)) - ?
                                   END AS INTEGER
                               ) AS overdue_days,
                               COALESCE(NULLIF(o.expected_delivery_date, ''), o.sent_at)
                                   AS reference_value,
                               o.delivery_status
                        FROM orders o
                        JOIN suppliers s ON s.id = o.supplier_id
                        WHERE o.deleted_at = '' AND o.archived_at = ''
                          AND o.sent_at <> ''
                          AND o.delivery_status IN (
                              'En attente', 'Partiellement livrée'
                          )
                          AND (
                              (o.expected_delivery_date <> ''
                               AND julianday(o.expected_delivery_date) < julianday(?))
                              OR
                              (o.expected_delivery_date = ''
                               AND julianday(?) - julianday(substr(o.sent_at, 1, 10)) >= ?)
                          )
                    ) alerts
                    ORDER BY overdue_days DESC, supplier_name COLLATE NOCASE
                    LIMIT ?
                    """,
                    (
                        reference_date.isoformat(),
                        reference_date.isoformat(),
                        max(1, confirmation_days),
                        reference_date.isoformat(),
                        reference_date.isoformat(),
                        max(1, delivery_days),
                        reference_date.isoformat(),
                        reference_date.isoformat(),
                        max(1, delivery_days),
                        limit,
                    ),
                )
            )

    def reorder_suggestions(
        self, reference_date: date | None = None, limit: int = 200
    ) -> list[sqlite3.Row]:
        reference_date = reference_date or date.today()
        with self.connect() as connection:
            return list(
                connection.execute(
                    f"""
                    WITH history AS (
                        SELECT DISTINCT ol.product_id, o.order_date
                        FROM order_lines ol
                        JOIN orders o ON o.id = ol.order_id
                        WHERE ol.product_id IS NOT NULL
                          AND o.deleted_at = '' AND o.sent_at <> ''
                    ), spaced AS (
                        SELECT product_id, order_date,
                               julianday(order_date) - julianday(
                                   LAG(order_date) OVER (
                                       PARTITION BY product_id ORDER BY order_date
                                   )
                               ) AS interval_days
                        FROM history
                    ), rhythm AS (
                        SELECT product_id, MAX(order_date) AS last_order_date,
                               AVG(interval_days) AS average_interval_days,
                               COUNT(interval_days) AS interval_count
                        FROM spaced
                        WHERE interval_days BETWEEN 1 AND 730
                        GROUP BY product_id
                    )
                    SELECT p.id AS product_id, p.supplier_id, p.supplier_name,
                           COALESCE(po.supplier_ref, p.supplier_ref) AS supplier_ref,
                           COALESCE(po.designation, p.designation) AS designation,
                           COALESCE(po.conditionnement, p.conditionnement) AS conditionnement,
                           COALESCE(po.unit_price, p.unit_price) AS unit_price,
                           COALESCE(po.vat, p.vat) AS vat,
                           p.usual_cartons, r.last_order_date,
                           ROUND(r.average_interval_days) AS average_interval_days,
                           CAST(
                               julianday(?) - julianday(r.last_order_date)
                               - r.average_interval_days AS INTEGER
                           ) AS overdue_days
                    FROM rhythm r
                    JOIN products p ON p.id = r.product_id
                    LEFT JOIN product_overrides po ON po.product_id = p.id
                    WHERE p.active = 1 AND r.interval_count >= 2
                      AND julianday(?) - julianday(r.last_order_date)
                          >= r.average_interval_days * 0.85
                    ORDER BY overdue_days DESC, p.supplier_name,
                             COALESCE(po.designation, p.designation)
                    LIMIT ?
                    """,
                    (
                        reference_date.isoformat(),
                        reference_date.isoformat(),
                        limit,
                    ),
                )
            )

    def find_recent_similar_order(
        self,
        supplier_id: int,
        lines: Sequence[Mapping[str, object]],
        days: int = 7,
    ) -> sqlite3.Row | None:
        requested = {
            str(line.get("product_id") or line.get("code_cahpp") or line.get("supplier_ref") or "")
            for line in lines
        }
        requested.discard("")
        if not requested:
            return None
        with self.connect() as connection:
            candidates = list(
                connection.execute(
                    """
                    SELECT o.id, o.order_number, o.order_date, o.status,
                           s.name AS supplier_name
                    FROM orders o JOIN suppliers s ON s.id = o.supplier_id
                    WHERE o.supplier_id = ? AND o.deleted_at = ''
                      AND julianday(o.order_date) >= julianday('now', ?)
                    ORDER BY o.order_date DESC, o.id DESC
                    """,
                    (supplier_id, f"-{max(1, days)} days"),
                )
            )
            for candidate in candidates:
                existing = {
                    str(
                        row["product_id"]
                        or row["code_cahpp"]
                        or row["supplier_ref"]
                        or ""
                    )
                    for row in connection.execute(
                        """
                        SELECT product_id, code_cahpp, supplier_ref
                        FROM order_lines WHERE order_id = ?
                        """,
                        (candidate["id"],),
                    )
                }
                existing.discard("")
                if existing == requested:
                    return candidate
        return None

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

    def reopen_unsent_order(self, order_id: int) -> None:
        """Invalide PDF et préparation mail sous transaction avant correction.

        Conserve numéro, lignes, pièces jointes et audit. Les copies externes
        ne peuvent pas être retirées : l'utilisateur doit les remplacer.
        """
        now = datetime.now().isoformat(timespec="microseconds")
        _, actor = self._actor()
        with self.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            order = connection.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            if order is None or not self.can_delete_unsent_order(order):
                raise ValueError("Une commande envoyée, supprimée ou déjà suivie ne peut pas être reprise.")
            if order["status"] == "Brouillon":
                return
            connection.execute(
                """UPDATE orders SET status = 'Brouillon', pdf_path = '',
                   email_prepared_at = '', updated_at = ?, updated_by = ?,
                   shared_revision = shared_revision + 1,
                   sync_state = 'À synchroniser' WHERE id = ?""", (now, actor, order_id),
            )
            self._record_order_audit(connection, order_id,
                "Commande reprise avant envoi", occurred_at=now,
                details="PDF et préparation e-mail invalidés ; régénération nécessaire.")

    def delete_draft(self, order_id: int) -> list[str]:
        return self.delete_unsent_order(order_id, drafts_only=True)

    @staticmethod
    def can_delete_unsent_order(order: Mapping[str, object]) -> bool:
        return (
            not order["deleted_at"]
            and order["status"] in {"Brouillon", "Générée", "E-mail préparé"}
            and not order["sent_at"]
            and not order["confirmed_at"]
            and not order["invoiced_at"]
            and order["delivery_status"] == "Non suivie"
        )

    def delete_unsent_order(
        self, order_id: int, *, drafts_only: bool = False
    ) -> list[str]:
        now = datetime.now().isoformat(timespec="seconds")
        _, actor_name = self._actor()
        with self.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            order = connection.execute(
                "SELECT * FROM orders WHERE id = ?",
                (order_id,),
            ).fetchone()
            if order is None or order["deleted_at"]:
                raise ValueError("Commande introuvable ou déjà supprimée.")
            if drafts_only and order["status"] != "Brouillon":
                raise ValueError(
                    "Seuls les brouillons peuvent être supprimés."
                )
            if not self.can_delete_unsent_order(order):
                raise ValueError(
                    "Une commande envoyée ou déjà suivie ne peut pas être supprimée."
                )
            stored_paths = [
                str(row["stored_path"] or "")
                for row in connection.execute(
                    """
                    SELECT stored_path FROM order_attachments
                    WHERE order_id = ?
                    """,
                    (order_id,),
                )
            ]
            self._record_order_audit(
                connection,
                order_id,
                "Brouillon supprimé" if order["status"] == "Brouillon"
                else "Commande non envoyée supprimée",
                occurred_at=now,
            )
            connection.execute(
                """
                UPDATE orders
                SET deleted_at = ?, deleted_by = ?, updated_at = ?,
                    updated_by = ?, shared_revision = shared_revision + 1,
                    sync_state = 'À synchroniser', notes = '',
                    total_ht = 0, total_vat = 0, total_ttc = 0,
                    pdf_path = ''
                WHERE id = ?
                """,
                (now, actor_name, now, actor_name, order_id),
            )
            connection.execute(
                "DELETE FROM order_lines WHERE order_id = ?", (order_id,)
            )
            connection.execute(
                "DELETE FROM order_receipts WHERE order_id = ?", (order_id,)
            )
            connection.execute(
                "DELETE FROM order_comments WHERE order_id = ?", (order_id,)
            )
            connection.execute(
                "DELETE FROM order_attachments WHERE order_id = ?",
                (order_id,),
            )
        return stored_paths

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
            requester_service=order["requester_service"] or "",
        )

    def duplicate_order_lines(
        self,
        order_id: int,
        line_uids: Sequence[str],
        selected_date: date | None = None,
        order_number: str | None = None,
        shared_uid: str | None = None,
    ) -> int:
        selected = {str(value) for value in line_uids}
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
            if str(line["line_uid"]) in selected
        ]
        if not duplicated_lines:
            raise ValueError("Sélectionnez au moins un article à recommander.")
        return self.save_order(
            supplier_id=int(order["supplier_id"]),
            lines=duplicated_lines,
            notes=order["notes"] or "",
            status="Brouillon",
            selected_date=selected_date or date.today(),
            order_number=order_number,
            shared_uid=shared_uid,
            requester_service=order["requester_service"] or "",
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
                      AND deleted_at = ''
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
            self._recompute_order_workflow(connection, order_id, now)
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
            sets.append(
                "delivery_status = CASE "
                "WHEN delivery_status = 'Non suivie' THEN 'En attente' "
                "ELSE delivery_status END"
            )
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

    def update_delivery_status(self, order_id: int, status: str) -> None:
        if status not in {"En attente", "Partiellement livrée", "Livrée"}:
            raise ValueError("État de livraison invalide.")
        now = datetime.now().isoformat(timespec="seconds")
        _, actor_name = self._actor()
        delivered_at = now if status == "Livrée" else ""
        delivered_by = actor_name if status == "Livrée" else ""
        with self.session() as connection:
            order = connection.execute(
                "SELECT sent_at FROM orders WHERE id = ?", (order_id,)
            ).fetchone()
            if order is None:
                raise ValueError("Commande introuvable.")
            if not order["sent_at"]:
                raise ValueError(
                    "La commande doit être marquée comme envoyée avant de "
                    "suivre sa livraison."
                )
            connection.execute(
                """
                UPDATE orders
                SET delivery_status = ?, delivered_at = ?, delivered_by = ?,
                    shared_revision = shared_revision + 1,
                    sync_state = 'À synchroniser', updated_at = ?,
                    updated_by = ?
                WHERE id = ?
                """,
                (
                    status,
                    delivered_at,
                    delivered_by,
                    now,
                    actor_name,
                    order_id,
                ),
            )
            self._recompute_order_workflow(connection, order_id, now)
            self._record_order_audit(
                connection,
                order_id,
                f"Livraison : {status}",
                occurred_at=now,
            )

    def _recompute_order_workflow(
        self,
        connection: sqlite3.Connection,
        order_id: int,
        now: str | None = None,
    ) -> str:
        order = connection.execute(
            "SELECT * FROM orders WHERE id = ?", (order_id,)
        ).fetchone()
        if order is None:
            raise ValueError("Commande introuvable.")
        if order["invoiced_at"]:
            status = "Facturée"
        elif order["delivery_status"] == "Livrée":
            status = "Livrée"
        elif order["delivery_status"] == "Partiellement livrée":
            status = "Partiellement livrée"
        elif order["confirmed_at"]:
            status = "Confirmée"
        elif order["sent_at"]:
            status = "Envoyée"
        elif order["email_prepared_at"]:
            status = "E-mail préparé"
        elif order["pdf_path"]:
            status = "Générée"
        else:
            status = "Brouillon"
        connection.execute(
            "UPDATE orders SET status = ?, updated_at = ? WHERE id = ?",
            (
                status,
                now or datetime.now().isoformat(timespec="seconds"),
                order_id,
            ),
        )
        return status

    def mark_order_confirmed(
        self,
        order_id: int,
        confirmed: bool = True,
        expected_delivery_date: date | None = None,
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        _, actor_name = self._actor()
        with self.session() as connection:
            order = connection.execute(
                "SELECT sent_at FROM orders WHERE id = ?", (order_id,)
            ).fetchone()
            if order is None:
                raise ValueError("Commande introuvable.")
            if confirmed and not order["sent_at"]:
                raise ValueError("La commande doit d'abord être envoyée.")
            connection.execute(
                """
                UPDATE orders
                SET confirmed_at = ?, confirmed_by = ?,
                    expected_delivery_date = ?,
                    shared_revision = shared_revision + 1,
                    sync_state = 'À synchroniser', updated_at = ?,
                    updated_by = ?
                WHERE id = ?
                """,
                (
                    now if confirmed else "",
                    actor_name if confirmed else "",
                    (
                        expected_delivery_date.isoformat()
                        if confirmed and expected_delivery_date
                        else ""
                    ),
                    now,
                    actor_name,
                    order_id,
                ),
            )
            self._recompute_order_workflow(connection, order_id, now)
            self._record_order_audit(
                connection,
                order_id,
                "Confirmation fournisseur" if confirmed else "Confirmation annulée",
                (
                    f"Livraison prévue : {expected_delivery_date.isoformat()}"
                    if confirmed and expected_delivery_date
                    else ""
                ),
                occurred_at=now,
            )

    def mark_order_invoiced(self, order_id: int, invoiced: bool = True) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        _, actor_name = self._actor()
        with self.session() as connection:
            order = connection.execute(
                "SELECT sent_at FROM orders WHERE id = ?", (order_id,)
            ).fetchone()
            if order is None:
                raise ValueError("Commande introuvable.")
            if invoiced and not order["sent_at"]:
                raise ValueError("La commande doit d'abord être envoyée.")
            connection.execute(
                """
                UPDATE orders
                SET invoiced_at = ?, invoiced_by = ?,
                    shared_revision = shared_revision + 1,
                    sync_state = 'À synchroniser', updated_at = ?,
                    updated_by = ?
                WHERE id = ?
                """,
                (
                    now if invoiced else "",
                    actor_name if invoiced else "",
                    now,
                    actor_name,
                    order_id,
                ),
            )
            self._recompute_order_workflow(connection, order_id, now)
            self._record_order_audit(
                connection,
                order_id,
                "Facture reçue" if invoiced else "Facturation annulée",
                occurred_at=now,
            )

    def update_expected_delivery_date(
        self, order_id: int, expected_delivery_date: date | None
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        _, actor_name = self._actor()
        with self.session() as connection:
            order = connection.execute(
                "SELECT sent_at FROM orders WHERE id = ?", (order_id,)
            ).fetchone()
            if order is None:
                raise ValueError("Commande introuvable.")
            if not order["sent_at"]:
                raise ValueError("La commande doit d'abord être envoyée.")
            value = (
                expected_delivery_date.isoformat()
                if expected_delivery_date is not None
                else ""
            )
            connection.execute(
                """
                UPDATE orders
                SET expected_delivery_date = ?,
                    shared_revision = shared_revision + 1,
                    sync_state = 'À synchroniser', updated_at = ?, updated_by = ?
                WHERE id = ?
                """,
                (value, now, actor_name, order_id),
            )
            self._record_order_audit(
                connection,
                order_id,
                "Date de livraison prévue modifiée",
                value or "Date supprimée",
                occurred_at=now,
            )

    def receipt_summary(self, order_id: int) -> dict[str, object]:
        with self.connect() as connection:
            order = connection.execute(
                """
                SELECT o.*, s.name AS supplier_name
                FROM orders o JOIN suppliers s ON s.id = o.supplier_id
                WHERE o.id = ?
                """,
                (order_id,),
            ).fetchone()
            if order is None:
                raise ValueError("Commande introuvable.")
            lines = list(
                connection.execute(
                    """
                    SELECT ol.*,
                           COALESCE(SUM(rl.quantity_received), 0) AS received_units,
                           MAX(0, ol.total_units -
                               COALESCE(SUM(rl.quantity_received), 0)
                           ) AS remaining_units
                    FROM order_lines ol
                    LEFT JOIN receipt_lines rl
                      ON rl.order_line_uid = ol.line_uid
                    WHERE ol.order_id = ?
                    GROUP BY ol.id
                    ORDER BY ol.line_order, ol.id
                    """,
                    (order_id,),
                )
            )
            receipts = list(
                connection.execute(
                    """
                    SELECT r.*,
                           COALESCE(SUM(rl.quantity_received), 0) AS total_received
                    FROM order_receipts r
                    LEFT JOIN receipt_lines rl ON rl.receipt_id = r.id
                    WHERE r.order_id = ?
                    GROUP BY r.id
                    ORDER BY r.receipt_date DESC, r.id DESC
                    """,
                    (order_id,),
                )
            )
        return {"order": order, "lines": lines, "receipts": receipts}

    def add_receipt(
        self,
        order_id: int,
        receipt_date: date,
        quantities: Mapping[str, float | int | Decimal],
        reference: str = "",
        notes: str = "",
        receipt_uid: str | None = None,
    ) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        _, actor_name = self._actor()
        prepared = {
            str(line_uid): money(quantity)
            for line_uid, quantity in quantities.items()
            if money(quantity) > 0
        }
        if not prepared:
            raise ValueError("Indiquez au moins une quantité reçue.")
        with self.session() as connection:
            order = connection.execute(
                "SELECT sent_at FROM orders WHERE id = ?", (order_id,)
            ).fetchone()
            if order is None:
                raise ValueError("Commande introuvable.")
            if not order["sent_at"]:
                raise ValueError("La commande doit être envoyée avant sa réception.")
            line_rows = {
                str(row["line_uid"]): row
                for row in connection.execute(
                    """
                    SELECT ol.line_uid, ol.designation, ol.total_units,
                           COALESCE(SUM(rl.quantity_received), 0) AS received
                    FROM order_lines ol
                    LEFT JOIN receipt_lines rl
                      ON rl.order_line_uid = ol.line_uid
                    WHERE ol.order_id = ?
                    GROUP BY ol.id
                    """,
                    (order_id,),
                )
            }
            for line_uid, quantity in prepared.items():
                line = line_rows.get(line_uid)
                if line is None:
                    raise ValueError("Une ligne de réception est inconnue.")
                remaining = money(line["total_units"]) - money(line["received"])
                if quantity > remaining:
                    raise ValueError(
                        f"La quantité reçue dépasse le reliquat pour « {line['designation']} » "
                        f"({float(remaining):g} restant)."
                    )
            cursor = connection.execute(
                """
                INSERT INTO order_receipts(
                    order_id, receipt_uid, receipt_date, reference, notes,
                    received_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    receipt_uid or str(uuid.uuid4()),
                    receipt_date.isoformat(),
                    reference.strip(),
                    notes.strip(),
                    actor_name,
                    now,
                    now,
                ),
            )
            receipt_id = int(cursor.lastrowid)
            connection.executemany(
                """
                INSERT INTO receipt_lines(
                    receipt_id, order_line_uid, quantity_received
                ) VALUES (?, ?, ?)
                """,
                (
                    (receipt_id, line_uid, float(quantity))
                    for line_uid, quantity in prepared.items()
                ),
            )
            totals = connection.execute(
                """
                SELECT COALESCE(SUM(ol.total_units), 0) AS ordered,
                       COALESCE((
                           SELECT SUM(rl.quantity_received)
                           FROM receipt_lines rl
                           JOIN order_receipts r ON r.id = rl.receipt_id
                           WHERE r.order_id = ?
                       ), 0) AS received
                FROM order_lines ol WHERE ol.order_id = ?
                """,
                (order_id, order_id),
            ).fetchone()
            ordered = money(totals["ordered"])
            received = money(totals["received"])
            delivery_status = "Livrée" if received >= ordered else "Partiellement livrée"
            connection.execute(
                """
                UPDATE orders
                SET delivery_status = ?, delivered_at = ?, delivered_by = ?,
                    shared_revision = shared_revision + 1,
                    sync_state = 'À synchroniser', updated_at = ?, updated_by = ?
                WHERE id = ?
                """,
                (
                    delivery_status,
                    now if delivery_status == "Livrée" else "",
                    actor_name if delivery_status == "Livrée" else "",
                    now,
                    actor_name,
                    order_id,
                ),
            )
            self._recompute_order_workflow(connection, order_id, now)
            self._record_order_audit(
                connection,
                order_id,
                "Réception enregistrée",
                reference.strip() or f"{float(received):g}/{float(ordered):g} unités reçues",
                occurred_at=now,
            )
        return receipt_id

    def delete_receipt(self, receipt_id: int) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        _, actor_name = self._actor()
        with self.session() as connection:
            receipt = connection.execute(
                "SELECT * FROM order_receipts WHERE id = ?", (receipt_id,)
            ).fetchone()
            if receipt is None:
                raise ValueError("Réception introuvable.")
            order_id = int(receipt["order_id"])
            connection.execute(
                "DELETE FROM order_receipts WHERE id = ?", (receipt_id,)
            )
            totals = connection.execute(
                """
                SELECT COALESCE(SUM(ol.total_units), 0) AS ordered,
                       COALESCE((
                           SELECT SUM(rl.quantity_received)
                           FROM receipt_lines rl JOIN order_receipts r
                             ON r.id = rl.receipt_id
                           WHERE r.order_id = ?
                       ), 0) AS received
                FROM order_lines ol WHERE ol.order_id = ?
                """,
                (order_id, order_id),
            ).fetchone()
            received = money(totals["received"])
            ordered = money(totals["ordered"])
            if received <= 0:
                delivery_status = "En attente"
            elif received >= ordered:
                delivery_status = "Livrée"
            else:
                delivery_status = "Partiellement livrée"
            connection.execute(
                """
                UPDATE orders
                SET delivery_status = ?, delivered_at = ?, delivered_by = ?,
                    shared_revision = shared_revision + 1,
                    sync_state = 'À synchroniser', updated_at = ?, updated_by = ?
                WHERE id = ?
                """,
                (
                    delivery_status,
                    now if delivery_status == "Livrée" else "",
                    actor_name if delivery_status == "Livrée" else "",
                    now,
                    actor_name,
                    order_id,
                ),
            )
            self._recompute_order_workflow(connection, order_id, now)
            self._record_order_audit(
                connection,
                order_id,
                "Réception supprimée",
                str(receipt["reference"] or receipt["receipt_date"]),
                occurred_at=now,
            )
        return order_id

    def list_order_comments(self, order_id: int) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT * FROM order_comments WHERE order_id = ?
                    ORDER BY created_at DESC, id DESC
                    """,
                    (order_id,),
                )
            )

    def add_order_comment(
        self,
        order_id: int,
        body: str,
        comment_uid: str | None = None,
    ) -> int:
        body = body.strip()
        if not body:
            raise ValueError("Le commentaire est vide.")
        now = datetime.now().isoformat(timespec="seconds")
        _, actor_name = self._actor()
        with self.session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO order_comments(
                    order_id, comment_uid, body, author_name, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (order_id, comment_uid or str(uuid.uuid4()), body, actor_name, now),
            )
            self._touch_order(connection, order_id, now)
            self._record_order_audit(
                connection, order_id, "Commentaire interne ajouté", occurred_at=now
            )
            return int(cursor.lastrowid)

    def delete_order_comment(self, comment_id: int) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        with self.session() as connection:
            comment = connection.execute(
                "SELECT * FROM order_comments WHERE id = ?", (comment_id,)
            ).fetchone()
            if comment is None:
                raise ValueError("Commentaire introuvable.")
            order_id = int(comment["order_id"])
            connection.execute(
                "DELETE FROM order_comments WHERE id = ?", (comment_id,)
            )
            self._touch_order(connection, order_id, now)
            self._record_order_audit(
                connection, order_id, "Commentaire interne supprimé", occurred_at=now
            )
        return order_id

    def set_order_archived(self, order_id: int, archived: bool) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        _, actor_name = self._actor()
        with self.session() as connection:
            order = connection.execute(
                "SELECT status FROM orders WHERE id = ?", (order_id,)
            ).fetchone()
            if order is None:
                raise ValueError("Commande introuvable.")
            if archived and order["status"] == "Brouillon":
                raise ValueError("Un brouillon ne peut pas être archivé.")
            connection.execute(
                """
                UPDATE orders
                SET archived_at = ?, archived_by = ?,
                    shared_revision = shared_revision + 1,
                    sync_state = 'À synchroniser', updated_at = ?,
                    updated_by = ?
                WHERE id = ?
                """,
                (
                    now if archived else "",
                    actor_name if archived else "",
                    now,
                    actor_name,
                    order_id,
                ),
            )
            self._record_order_audit(
                connection,
                order_id,
                "Commande archivée" if archived else "Commande restaurée",
                occurred_at=now,
            )

    def archive_old_orders(self, before_date: date) -> list[int]:
        now = datetime.now().isoformat(timespec="seconds")
        _, actor_name = self._actor()
        with self.session() as connection:
            order_ids = [
                int(row["id"])
                for row in connection.execute(
                    """
                    SELECT id FROM orders
                    WHERE deleted_at = '' AND archived_at = ''
                      AND delivery_status = 'Livrée' AND order_date < ?
                    ORDER BY order_date, id
                    """,
                    (before_date.isoformat(),),
                )
            ]
            for order_id in order_ids:
                connection.execute(
                    """
                    UPDATE orders
                    SET archived_at = ?, archived_by = ?,
                        shared_revision = shared_revision + 1,
                        sync_state = 'À synchroniser', updated_at = ?,
                        updated_by = ?
                    WHERE id = ?
                    """,
                    (now, actor_name, now, actor_name, order_id),
                )
                self._record_order_audit(
                    connection,
                    order_id,
                    "Commande archivée automatiquement",
                    occurred_at=now,
                )
            connection.execute("PRAGMA optimize")
        return order_ids

    def statistics(
        self, date_from: date, date_to: date, supplier_id: int | None = None
    ) -> dict[str, object]:
        parameters = [date_from.isoformat(), date_to.isoformat()]
        order_filter = """
            o.deleted_at = '' AND o.sent_at <> ''
            AND o.order_date BETWEEN ? AND ?
        """
        if supplier_id is not None:
            order_filter += " AND o.supplier_id = ?"
            parameters.append(supplier_id)
        with self.connect() as connection:
            summary = connection.execute(
                f"""
                SELECT COUNT(*) AS order_count,
                       COUNT(DISTINCT o.supplier_id) AS supplier_count,
                       COALESCE(SUM(o.total_ht), 0) AS total_ht,
                       COALESCE(SUM(o.total_ttc), 0) AS total_ttc
                FROM orders o WHERE {order_filter}
                """,
                parameters,
            ).fetchone()
            suppliers = list(
                connection.execute(
                    f"""
                    SELECT s.name AS supplier_name,
                           COUNT(*) AS order_count,
                           COALESCE(SUM(o.total_ht), 0) AS total_ht,
                           COALESCE(SUM(o.total_ttc), 0) AS total_ttc,
                           ROUND(AVG(
                               CASE WHEN o.confirmed_at <> '' THEN
                                   julianday(o.confirmed_at) - julianday(o.sent_at)
                               END
                           ), 1) AS average_confirmation_days,
                           ROUND(AVG(
                               CASE WHEN o.delivered_at <> '' THEN
                                   julianday(o.delivered_at) - julianday(o.sent_at)
                               END
                           ), 1) AS average_delivery_days,
                           SUM(
                               CASE WHEN o.delivery_status IN (
                                   'En attente', 'Partiellement livrée'
                               ) THEN 1 ELSE 0 END
                           ) AS incomplete_count
                    FROM orders o
                    JOIN suppliers s ON s.id = o.supplier_id
                    WHERE {order_filter}
                    GROUP BY s.id, s.name
                    ORDER BY total_ht DESC, s.name COLLATE NOCASE
                    """,
                    parameters,
                )
            )
            products = list(
                connection.execute(
                    f"""
                    SELECT s.name AS supplier_name, ol.supplier_ref,
                           ol.designation,
                           COALESCE(SUM(ol.cartons), 0) AS cartons,
                           COALESCE(SUM(ol.total_units), 0) AS total_units,
                           COALESCE(SUM(ol.total_ht), 0) AS total_ht
                    FROM order_lines ol
                    JOIN orders o ON o.id = ol.order_id
                    JOIN suppliers s ON s.id = o.supplier_id
                    WHERE {order_filter}
                    GROUP BY s.name, ol.supplier_ref, ol.designation
                    ORDER BY total_ht DESC, ol.designation COLLATE NOCASE

                    """,
                    parameters,
                )
            )
            price_variances = list(
                connection.execute(
                    f"""
                    WITH ranked AS (
                        SELECT ol.product_id, s.name AS supplier_name,
                               ol.supplier_ref, ol.designation,
                               ol.unit_price AS ordered_price,
                               o.order_date, o.order_number,
                               ROW_NUMBER() OVER (
                                   PARTITION BY ol.product_id
                                   ORDER BY o.order_date DESC, o.id DESC
                               ) AS position
                        FROM order_lines ol
                        JOIN orders o ON o.id = ol.order_id
                        JOIN suppliers s ON s.id = o.supplier_id
                        WHERE {order_filter} AND ol.product_id IS NOT NULL
                    )
                    SELECT r.supplier_name, r.supplier_ref, r.designation,
                           r.order_number, r.order_date, r.ordered_price,
                           COALESCE(po.unit_price, p.unit_price) AS current_price,
                           COALESCE(po.unit_price, p.unit_price) - r.ordered_price
                               AS difference,
                           CASE WHEN r.ordered_price <> 0 THEN
                               100 * (
                                   COALESCE(po.unit_price, p.unit_price)
                                   - r.ordered_price
                               ) / r.ordered_price
                           ELSE 0 END AS difference_percent
                    FROM ranked r
                    JOIN products p ON p.id = r.product_id
                    LEFT JOIN product_overrides po ON po.product_id = p.id
                    WHERE r.position = 1
                      AND COALESCE(po.unit_price, p.unit_price) IS NOT NULL
                      AND ABS(
                          COALESCE(po.unit_price, p.unit_price) - r.ordered_price
                      ) > 0.00005
                    ORDER BY ABS(difference_percent) DESC, r.designation

                    """,
                    parameters,
                )
            )
        return {
            "summary": dict(summary) if summary else {},
            "suppliers": suppliers,
            "products": products,
            "price_variances": price_variances,
        }

    def quick_integrity_check(self) -> tuple[bool, str]:
        with self.connect() as connection:
            result = [
                str(row[0])
                for row in connection.execute("PRAGMA quick_check")
            ]
        return result == ["ok"], "; ".join(result)

    def optimize_database(self) -> None:
        with self.session() as connection:
            connection.execute("PRAGMA optimize")
        with self.connect() as connection:
            connection.execute("PRAGMA wal_checkpoint(PASSIVE)")

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

    def update_attachment_properties(
        self,
        attachment_id: int,
        kind: str,
        include_in_email: bool,
    ) -> None:
        kind = kind.strip()
        if not kind:
            raise ValueError("Le type de document est obligatoire.")
        now = datetime.now().isoformat(timespec="seconds")
        with self.session() as connection:
            attachment = connection.execute(
                """
                SELECT order_id, display_name FROM order_attachments
                WHERE id = ?
                """,
                (attachment_id,),
            ).fetchone()
            if attachment is None:
                raise ValueError("Document introuvable.")
            connection.execute(
                """
                UPDATE order_attachments
                SET kind = ?, include_in_email = ?
                WHERE id = ?
                """,
                (kind, int(include_in_email), attachment_id),
            )
            self._touch_order(connection, attachment["order_id"], now)
            self._record_order_audit(
                connection,
                attachment["order_id"],
                f"Document reclassé : {attachment['display_name']} ({kind})",
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
                           internal_notes, replacement_code_cahpp,
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
                           po.unit_price, po.vat, po.updated_at, po.updated_by,
                           po.validated_catalog_token
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
                           p.internal_notes, p.replacement_code_cahpp,
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
                        repair_supplier_contact_value(
                            "contact_name", record.get("contact_name")
                        ),
                        repair_supplier_contact_value(
                            "email", record.get("email")
                        ),
                        repair_supplier_contact_value(
                            "phone", record.get("phone")
                        ),
                        record.get("address") or "",
                        repair_supplier_contact_value(
                            "website", record.get("website")
                        ),
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
                        usual_cartons, short_name, internal_notes,
                        replacement_code_cahpp, created_by, updated_by,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'LOCAL', ?, ?, ?,
                              ?, ?, ?, ?, ?, ?)
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
                        internal_notes = excluded.internal_notes,
                        replacement_code_cahpp = excluded.replacement_code_cahpp,
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
                        record.get("internal_notes") or "",
                        record.get("replacement_code_cahpp") or "",
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
                        internal_notes, replacement_code_cahpp,
                        updated_at, updated_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(code_cahpp) DO UPDATE SET
                        favorite = excluded.favorite,
                        usual_cartons = excluded.usual_cartons,
                        short_name = excluded.short_name,
                        internal_notes = excluded.internal_notes,
                        replacement_code_cahpp = excluded.replacement_code_cahpp,
                        updated_at = excluded.updated_at,
                        updated_by = excluded.updated_by
                    """,
                    (
                        code,
                        int(bool(record.get("favorite", 0))),
                        record.get("usual_cartons") or 1,
                        record.get("short_name") or "",
                        record.get("internal_notes") or "",
                        record.get("replacement_code_cahpp") or "",
                        record.get("updated_at") or "",
                        record.get("updated_by") or "",
                    ),
                )
                connection.execute(
                    """
                    UPDATE products
                    SET favorite = ?, usual_cartons = ?, short_name = ?,
                        internal_notes = ?, replacement_code_cahpp = ?
                    WHERE code_cahpp = ?
                    """,
                    (
                        int(bool(record.get("favorite", 0))),
                        record.get("usual_cartons") or 1,
                        record.get("short_name") or "",
                        record.get("internal_notes") or "",
                        record.get("replacement_code_cahpp") or "",
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
                        unit_packaging, unit_price, vat, updated_at, updated_by, validated_catalog_token
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(product_id) DO UPDATE SET
                        supplier_ref = excluded.supplier_ref,
                        designation = excluded.designation,
                        conditionnement = excluded.conditionnement,
                        unit_packaging = excluded.unit_packaging,
                        unit_price = excluded.unit_price,
                        vat = excluded.vat,
                        updated_at = excluded.updated_at,
                        updated_by = excluded.updated_by,
                        validated_catalog_token = excluded.validated_catalog_token
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
                        record.get("validated_catalog_token") or "",
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
            receipts = []
            for receipt in connection.execute(
                """
                SELECT * FROM order_receipts
                WHERE order_id = ? ORDER BY receipt_date, id
                """,
                (order_id,),
            ):
                item = dict(receipt)
                item["lines"] = [
                    dict(row)
                    for row in connection.execute(
                        """
                        SELECT order_line_uid, quantity_received
                        FROM receipt_lines WHERE receipt_id = ? ORDER BY id
                        """,
                        (receipt["id"],),
                    )
                ]
                item.pop("id", None)
                item.pop("order_id", None)
                receipts.append(item)
            comments = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT comment_uid, body, author_name, created_at
                    FROM order_comments WHERE order_id = ?
                    ORDER BY created_at, id
                    """,
                    (order_id,),
                )
            ]
        order_values = {
            key: order[key]
            for key in (
                "order_number",
                "order_date",
                "requester_service",
                "status",
                "notes",
                "total_ht",
                "total_vat",
                "total_ttc",
                "pdf_path",
                "email_prepared_at",
                "sent_at",
                "confirmed_at",
                "confirmed_by",
                "delivery_status",
                "delivered_at",
                "delivered_by",
                "invoiced_at",
                "invoiced_by",
                "expected_delivery_date",
                "archived_at",
                "archived_by",
                "shared_uid",
                "shared_revision",
                "catalog_hash",
                "created_by",
                "updated_by",
                "sent_by",
                "deleted_at",
                "deleted_by",
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
                        "line_uid",
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
            "receipts": receipts,
            "comments": comments,
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
                WHERE shared_uid = ?
                LIMIT 1
                """,
                (shared_uid,),
            ).fetchone()
            collision = connection.execute(
                "SELECT shared_uid FROM orders WHERE order_number=? AND shared_uid<>?",
                (order_number, shared_uid),
            ).fetchone()
            if collision:
                raise ValueError(
                    "Conflit d'identité : ce numéro appartient à une autre commande. Aucune donnée remplacée."
                )
            remote_revision = int(order.get("shared_revision") or 0)
            if existing is not None:
                if existing["sync_state"] != "Synchronisée":
                    if remote_revision != int(existing["sync_base_revision"]):
                        raise ValueError(
                            "Conflit de synchronisation : modifications locales conservées, version distante différente."
                        )
                    return int(existing["id"]), False
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
                order.get("requester_service") or "",
                order.get("status") or "Brouillon",
                order.get("notes") or "",
                order.get("total_ht") or 0,
                order.get("total_vat") or 0,
                order.get("total_ttc") or 0,
                order.get("pdf_path") or "",
                order.get("email_prepared_at") or "",
                order.get("sent_at") or "",
                order.get("confirmed_at") or "",
                order.get("confirmed_by") or "",
                order.get("delivery_status")
                or ("En attente" if order.get("sent_at") else "Non suivie"),
                order.get("delivered_at") or "",
                order.get("delivered_by") or "",
                order.get("invoiced_at") or "",
                order.get("invoiced_by") or "",
                order.get("expected_delivery_date") or "",
                order.get("archived_at") or "",
                order.get("archived_by") or "",
                shared_uid,
                remote_revision,
                "Synchronisée",
                order.get("catalog_hash") or "",
                order.get("created_by") or "",
                order.get("updated_by") or "",
                order.get("sent_by") or "",
                order.get("deleted_at") or "",
                order.get("deleted_by") or "",
                now,
                order.get("created_at") or now,
                order.get("updated_at") or now,
            )
            if existing is None:
                cursor = connection.execute(
                    """
                    INSERT INTO orders(
                        order_number, supplier_id, order_date, requester_service,
                        status, notes,
                        total_ht, total_vat, total_ttc, pdf_path,
                        email_prepared_at, sent_at, confirmed_at, confirmed_by,
                        delivery_status, delivered_at, delivered_by,
                        invoiced_at, invoiced_by, expected_delivery_date,
                        archived_at, archived_by,
                        shared_uid,
                        shared_revision, sync_state, catalog_hash,
                        created_by, updated_by, sent_by, deleted_at, deleted_by,
                        last_synced_at,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                              ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        requester_service = ?, status = ?, notes = ?,
                        total_ht = ?, total_vat = ?,
                        total_ttc = ?, pdf_path = ?, email_prepared_at = ?,
                        sent_at = ?, confirmed_at = ?, confirmed_by = ?,
                        delivery_status = ?, delivered_at = ?, delivered_by = ?,
                        invoiced_at = ?, invoiced_by = ?,
                        expected_delivery_date = ?, archived_at = ?, archived_by = ?,
                        shared_uid = ?, shared_revision = ?, sync_state = ?,
                        catalog_hash = ?, created_by = ?, updated_by = ?,
                        sent_by = ?, deleted_at = ?, deleted_by = ?,
                        last_synced_at = ?,
                        created_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (*values, order_id),
                )
                connection.execute(
                    "DELETE FROM order_receipts WHERE order_id = ?", (order_id,)
                )
                connection.execute(
                    "DELETE FROM order_comments WHERE order_id = ?", (order_id,)
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
                        order_id, line_uid, product_id, code_cahpp, supplier_ref,
                        designation, cartons, units_per_carton, total_units,
                        unit_price, vat, total_ht, line_order
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        item.get("line_uid") or str(uuid.uuid4()),
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
            for receipt in list(payload.get("receipts") or []):
                item = dict(receipt)
                cursor = connection.execute(
                    """
                    INSERT INTO order_receipts(
                        order_id, receipt_uid, receipt_date, reference, notes,
                        received_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        item.get("receipt_uid") or str(uuid.uuid4()),
                        item.get("receipt_date") or date.today().isoformat(),
                        item.get("reference") or "",
                        item.get("notes") or "",
                        item.get("received_by") or "",
                        item.get("created_at") or now,
                        item.get("updated_at") or now,
                    ),
                )
                receipt_id = int(cursor.lastrowid)
                for receipt_line in list(item.get("lines") or []):
                    line_item = dict(receipt_line)
                    connection.execute(
                        """
                        INSERT INTO receipt_lines(
                            receipt_id, order_line_uid, quantity_received
                        ) VALUES (?, ?, ?)
                        """,
                        (
                            receipt_id,
                            line_item.get("order_line_uid") or "",
                            line_item.get("quantity_received") or 0,
                        ),
                    )
            for comment in list(payload.get("comments") or []):
                item = dict(comment)
                connection.execute(
                    """
                    INSERT INTO order_comments(
                        order_id, comment_uid, body, author_name, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        item.get("comment_uid") or str(uuid.uuid4()),
                        item.get("body") or "",
                        item.get("author_name") or "",
                        item.get("created_at") or now,
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
            connection.execute(
                "UPDATE orders SET sync_base_revision=? WHERE id=?",
                (remote_revision, order_id),
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
                    """
                    SELECT id FROM orders
                    WHERE deleted_at = ''
                    ORDER BY id
                    """
                )
            ]

    def mark_order_synced(self, order_id: int) -> None:
        with self.session() as connection:
            connection.execute(
                """
                UPDATE orders
                SET sync_state = 'Synchronisée', sync_base_revision=shared_revision, last_synced_at = ?
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

    def rebuild_search(
        self, connection: sqlite3.Connection | None = None, *, manual: bool = False,
    ) -> bool:
        """Recrée uniquement l'index dérivé, avec rollback et contrôle avant validation."""
        with self._fts_lock:
            started = time.perf_counter()
            owns_connection = connection is None
            savepoint = False
            report: dict[str, object] = {
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "origin": "Manuelle" if manual else "Import" if connection else "Automatique",
                "success": False,
            }
            self.last_search_repair = report
            logger.info("fts_reconstruction_debut manuelle=%s", manual)
            try:
                connection = connection or self.connect()
                connection.execute("SAVEPOINT cahpp_search_rebuild")
                savepoint = True
                connection.execute("DROP TABLE IF EXISTS product_search")
                self._create_search_table(connection)
                connection.execute(
                    """INSERT INTO product_search(
                           rowid, code_cahpp, supplier_ref, designation, supplier_name
                       )
                       SELECT p.id, p.code_cahpp,
                              COALESCE(po.supplier_ref, p.supplier_ref),
                              COALESCE(po.designation, p.designation), p.supplier_name
                       FROM products p
                       LEFT JOIN product_overrides po ON po.product_id = p.id"""
                )
                connection.execute(
                    "INSERT INTO product_search(product_search) VALUES('integrity-check')"
                )
                self._probe_search_index(connection)
                products = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
                indexed = connection.execute("SELECT COUNT(*) FROM product_search").fetchone()[0]
                if products != indexed:
                    raise SearchIndexError("Le nombre d'articles indexés est incorrect.")
                connection.execute("RELEASE cahpp_search_rebuild")
                savepoint = False
                if owns_connection:
                    connection.commit()
                report.update({
                    "success": True, "products": products, "indexed": indexed,
                    "detail": "Index recréé ; intégrité FTS5 et recherche avec classement vérifiées.",
                })
            except (sqlite3.DatabaseError, SearchIndexError) as exc:
                if savepoint:
                    try:
                        connection.execute("ROLLBACK TO cahpp_search_rebuild")
                        connection.execute("RELEASE cahpp_search_rebuild")
                    except sqlite3.DatabaseError as rollback_error:
                        log_failure(logger, "fts_rollback_echec", rollback_error)
                self.fts_available = False
                self._fts_verified = False
                report.update({
                    "detail": self._search_index_failure(exc, "Reconstruction"),
                    "error_type": type(exc).__name__,
                    "sqlite_code": getattr(exc, "sqlite_errorname", ""),
                })
                self._fts_status_cache = {
                    "available": False, "consistent": False, "functional": False,
                    "error": self.fts_error, "repaired": False,
                }
                self._fts_retry_after = 0 if manual else time.monotonic() + 30
                return False
            finally:
                if owns_connection and connection is not None:
                    connection.close()
                report["finished_at"] = datetime.now().isoformat(timespec="seconds")
                report["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
                logger.info("fts_reconstruction_fin succes=%s duree_ms=%d",
                            report["success"], report["elapsed_ms"])
            self.fts_available = True
            self.fts_error = ""
            self._fts_verified = False
            self._fts_status_cache = {}
            self._fts_retry_after = 0
            self._search_stats_prepared = False
            self._search_stats_retry_after = 0
            return True

    def backup(self, destination: Path | str) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as source, closing(sqlite3.connect(destination)) as target:
            source.backup(target)
        return destination

    def diagnostic_snapshot(self) -> dict[str, object]:
        size = self.path.stat().st_size if self.path.is_file() else 0
        wal_path = self.path.with_name(self.path.name + "-wal")
        shm_path = self.path.with_name(self.path.name + "-shm")
        search_index = self.search_index_status(deep=True)
        with self.connect() as connection:
            quick_check = [
                str(row[0]) for row in connection.execute("PRAGMA quick_check")
            ]
            synchronization = [
                dict(r)
                for r in connection.execute(
                    "SELECT shared_revision AS local_revision, sync_base_revision AS base_revision FROM orders WHERE sync_state<>'Synchronisée'"
                )
            ]
            schema_version = int(
                connection.execute("PRAGMA user_version").fetchone()[0]
            )
            journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0])
            counts = {
                "products": int(
                    connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
                ),
                "active_products": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM products WHERE active = 1"
                    ).fetchone()[0]
                ),
                "suppliers": int(
                    connection.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0]
                ),
                "orders": int(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM orders
                        WHERE deleted_at = ''
                        """
                    ).fetchone()[0]
                ),
                "deleted_drafts": int(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM orders
                        WHERE deleted_at <> ''
                        """
                    ).fetchone()[0]
                ),
                "archived_orders": int(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM orders
                        WHERE archived_at <> '' AND deleted_at = ''
                        """
                    ).fetchone()[0]
                ),
                "pending_deliveries": int(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM orders
                        WHERE deleted_at = '' AND archived_at = ''
                          AND sent_at <> ''
                          AND delivery_status IN (
                              'En attente', 'Partiellement livrée'
                          )
                        """
                    ).fetchone()[0]
                ),
                "pending_orders": int(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM orders
                        WHERE sync_state <> 'Synchronisée'
                        """
                    ).fetchone()[0]
                ),
                "attachments": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM order_attachments"
                    ).fetchone()[0]
                ),
                "receipts": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM order_receipts"
                    ).fetchone()[0]
                ),
                "internal_comments": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM order_comments"
                    ).fetchone()[0]
                ),
                "imports": int(
                    connection.execute("SELECT COUNT(*) FROM imports").fetchone()[0]
                ),
                "catalog_reviews": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM products p LEFT JOIN product_overrides po ON po.product_id=p.id WHERE p.active=1 AND "
                        + CATALOG_REVIEW_SQL
                    ).fetchone()[0]
                ),
            }
            anomalies = {
                "orders_without_shared_uid": int(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM orders
                        WHERE shared_uid IS NULL OR shared_uid = ''
                        """
                    ).fetchone()[0]
                ),
                "orphan_order_lines": int(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM order_lines ol
                        LEFT JOIN orders o ON o.id = ol.order_id
                        WHERE o.id IS NULL
                        """
                    ).fetchone()[0]
                ),
                "orphan_attachments": int(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM order_attachments oa
                        LEFT JOIN orders o ON o.id = oa.order_id
                        WHERE o.id IS NULL
                        """
                    ).fetchone()[0]
                ),
            }
        return {
            "path": str(self.path.resolve()),
            "size_bytes": size,
            "wal_size_bytes": wal_path.stat().st_size if wal_path.is_file() else 0,
            "shm_size_bytes": shm_path.stat().st_size if shm_path.is_file() else 0,
            "schema_version": schema_version,
            "pending_revision_bases": synchronization,
            "catalog_publication_pending": bool(
                self.get_settings().get("horizon_catalog_pending")
            ),
            "journal_mode": journal_mode,
            "fts_available": self.fts_available,
            "search_index": search_index,
            "last_search_repair": dict(self.last_search_repair),
            "search_plan_preparation": dict(self.search_plan_preparation),
            "catalog_search_plan": self.catalog_search_plan(),
            "quick_check": quick_check,
            "counts": counts,
            "catalog_effective_period": self.get_settings().get(
                "catalog_effective_period", ""
            ),
            "anomalies": anomalies,
        }
