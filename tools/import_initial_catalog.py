from __future__ import annotations

import sys
from pathlib import Path

from cahpp_app.catalog_importer import CatalogImporter
from cahpp_app.database import Database


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(
            "Usage: python tools/import_initial_catalog.py CATALOGUE.xlsx BASE.sqlite3"
        )
    catalogue = Path(sys.argv[1]).resolve()
    database_path = Path(sys.argv[2]).resolve()
    database = Database(database_path)

    def progress(current: int, total: int, message: str) -> None:
        print(f"[{current:3d}%] {message}", flush=True)

    result = CatalogImporter(database).import_file(catalogue, progress)
    print(result)


if __name__ == "__main__":
    main()

