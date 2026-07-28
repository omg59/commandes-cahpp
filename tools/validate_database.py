from __future__ import annotations

import sys
import time
from pathlib import Path

from cahpp_app.database import Database


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python -m tools.validate_database BASE.sqlite3"
        )
    database = Database(Path(sys.argv[1]))
    with database.connect() as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        product_count = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        active_count = connection.execute(
            "SELECT COUNT(*) FROM products WHERE active = 1"
        ).fetchone()[0]
        search_count = connection.execute(
            "SELECT COUNT(*) FROM product_search"
        ).fetchone()[0]
        supplier_count = connection.execute(
            "SELECT COUNT(*) FROM suppliers"
        ).fetchone()[0]
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    started = time.perf_counter()
    results = database.search_products("gant toilette molletonne")
    duration = (time.perf_counter() - started) * 1000
    print(
        {
            "integrity": integrity,
            "products": product_count,
            "active": active_count,
            "search_index": search_count,
            "suppliers": supplier_count,
            "search_results": len(results),
            "search_ms": round(duration, 2),
        }
    )
    if integrity != "ok":
        raise RuntimeError("La base SQLite est corrompue.")
    if product_count != search_count:
        raise RuntimeError("L'index de recherche est incomplet.")


if __name__ == "__main__":
    main()
