"""Stockage décimal des montants dans SQLite et migration des anciennes valeurs."""

from __future__ import annotations

import re
import sqlite3
import tempfile
from contextlib import closing
from decimal import Decimal
from pathlib import Path

from .numbers import add_decimal, parse_decimal

SCHEMA_VERSION = 17

MONEY_COLUMNS = {
    "suppliers": ("franco_ht", "minimum_order_ht"),
    "products": ("unit_price", "gam_price"),
    "product_overrides": ("unit_price",),
    "price_history": ("unit_price",),
    "orders": ("total_ht", "total_vat", "total_ttc"),
    "order_lines": ("unit_price", "total_ht"),
}


def decimal_text(value) -> str | None:
    if value is None:
        return None
    number = parse_decimal(value, "Montant")
    if not number:
        return "0"
    # Éviter une allocation démesurée issue d'un exposant entré en texte.
    if not -1000 <= number.adjusted() <= 1000 or number.as_tuple().exponent < -1000:
        raise ValueError("La précision ou la taille du montant est hors limites.")
    result = format(number, "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def wire_amounts(row):
    """Les formats JSON partagés portent les montants sous forme de texte."""
    return {
        key: decimal_text(row[key]) if isinstance(row[key], Decimal) else row[key]
        for key in row.keys()
    }


def unit_price_decimals(value):
    return max(4, len((decimal_text(value) or "").partition(".")[2]))


sqlite3.register_converter("DECIMAL_TEXT", lambda value: Decimal(value.decode("ascii")))


class DecimalSum:
    def __init__(self):
        self.total = Decimal(0)

    def step(self, value):
        if value is not None:
            self.total = add_decimal(self.total, Decimal(value))

    def finalize(self):
        return format(self.total, "f")


def register_money_sql(connection):
    connection.create_function("cahpp_decimal", 1, decimal_text, deterministic=True)
    connection.create_aggregate("decimal_sum", 1, DecimalSum)

    def compare_decimal(left, right):
        a, b = Decimal(left), Decimal(right)
        return (a > b) - (a < b)

    connection.create_collation("CAHPP_DECIMAL", compare_decimal)


def _replace_money_table(connection, table, fields):
    table_info = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    if all(row["type"] == "DECIMAL_TEXT" for row in table_info if row["name"] in fields):
        return
    schema = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()[0]
    temporary = f"money17_{table}"
    declaration = schema[schema.index("("):]
    for column in fields:
        pattern = rf'([,(]\s*"?{column}"?\s+)([A-Z_]+)'
        declaration, count = re.subn(pattern, r"\g<1>DECIMAL_TEXT", declaration, flags=re.I)
        if count != 1:
            raise ValueError(f"Colonne monétaire introuvable dans le schéma : {table}.{column}.")
    objects = connection.execute(
        "SELECT sql FROM sqlite_master WHERE tbl_name=? AND type IN ('index','trigger') AND sql IS NOT NULL",
        (table,),
    ).fetchall()
    sequence = connection.execute("SELECT seq FROM sqlite_sequence WHERE name=?", (table,)).fetchone()
    columns = [f'"{row["name"]}"' for row in table_info]
    projected = [f"cahpp_decimal({name})" if row["name"] in fields else name
                 for name, row in zip(columns, table_info)]
    connection.execute(f'CREATE TABLE "{temporary}" {declaration}')
    connection.execute(f'INSERT INTO "{temporary}" ({",".join(columns)}) SELECT {",".join(projected)} FROM "{table}"')
    connection.execute(f'DROP TABLE "{table}"')
    connection.execute(f'ALTER TABLE "{temporary}" RENAME TO "{table}"')
    if sequence:
        connection.execute("DELETE FROM sqlite_sequence WHERE name=?", (table,))
        connection.execute("INSERT INTO sqlite_sequence(name,seq) VALUES (?,?)", (table, sequence[0]))
    for statement, in objects:
        connection.execute(statement)


def migrate_amounts(connection, path: Path):
    if connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION:
        return None
    # Nécessaire au remplacement des tables parentes sans déclenchement des
    # cascades. Le contrôle de toutes les références précède le commit.
    connection.execute("PRAGMA foreign_keys=OFF")
    connection.execute("PRAGMA legacy_alter_table=ON")
    try:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute("PRAGMA user_version").fetchone()[0] >= SCHEMA_VERSION:
            connection.commit()
            return None
        legacy = any(
            row["name"] in fields and row["type"] != "DECIMAL_TEXT"
            for table, fields in MONEY_COLUMNS.items()
            for row in connection.execute(f'PRAGMA table_info("{table}")')
        )
        backup = None
        if legacy:
            with tempfile.NamedTemporaryFile(prefix=f"{path.stem}-avant-montants-v17-", suffix=".sqlite3",
                                             dir=path.parent, delete=False) as stream:
                backup = Path(stream.name)
            try:
                with (closing(sqlite3.connect(path)) as source,
                      closing(sqlite3.connect(backup)) as destination):
                    source.backup(destination)
            except Exception:
                backup.unlink(missing_ok=True)
                raise
            for table, fields in MONEY_COLUMNS.items():
                try:
                    _replace_money_table(connection, table, fields)
                except sqlite3.DatabaseError as error:
                    raise ValueError(
                        f"Migration des montants interrompue pour « {table} ». "
                        f"La base a été conservée et sa copie se trouve dans « {backup.name} »."
                    ) from error
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise ValueError("Une référence SQLite est invalide. La migration des montants a été annulée.")
            connection.execute("UPDATE mobile_catalog_clock SET revision=revision+1 WHERE id=1")
        connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        connection.commit()
        return backup
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA legacy_alter_table=OFF")
        connection.execute("PRAGMA foreign_keys=ON")
