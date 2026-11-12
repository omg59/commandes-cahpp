"""Migration d'un profil rempli créé par le moteur exact de la bêta 5."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

BASELINE = "e0413b3b814f6bd793436447adf725a604d1ecce"
TABLES = (
    "suppliers",
    "products",
    "orders",
    "order_lines",
    "order_receipts",
    "receipt_lines",
    "order_comments",
    "order_attachments",
    "settings",
)


def snapshot(db):
    with db.connect() as connection:
        result = {}
        for table in TABLES:
            rows = [
                dict(r)
                for r in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")
            ]
            if table == "orders":
                for row in rows:
                    row.pop("sync_base_revision", None)
            result[table] = rows
        return result


def seed(profile):
    from cahpp_app.horizon.bootstrap import initialize_profile
    from cahpp_app.horizon.services import Cart
    from cahpp_app.pdf_export import generate_order_pdf
    from datetime import date

    profile.mkdir(parents=True, exist_ok=True)
    initialize_profile(profile)
    source = subprocess.check_output(
        ["git", "show", BASELINE + ":cahpp_app/database.py"]
    )
    with tempfile.TemporaryDirectory() as temporary:
        engine = Path(temporary) / "database.py"
        engine.write_bytes(source)
        spec = importlib.util.spec_from_file_location(
            "cahpp_app._beta5_database", engine
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        db = module.Database(profile / "data/commandes_cahpp.sqlite3")
    with db.session() as c:
        sid = c.execute(
            "INSERT INTO suppliers(name,email,customer_number) VALUES ('Fournisseur migration','test@example.invalid','CLIENT-42')"
        ).lastrowid
    pid = db.create_manual_product(sid, "MIGRATION", "Article conservé", 10, 2.5, 20)
    db.save_settings(
        {
            "establishment_name": "Établissement migration",
            "user_name": "Utilisateur migration",
            "user_id": "c983fe82-666c-4b07-8a1b-a76f183273a2",
        }
    )
    cart = Cart()
    cart.add(db.get_product(pid), quantity=2)
    oid = cart.save(db, notes="Note conservée", service="Unité migration")
    generate_order_pdf(db, oid, profile / "documents/2026-11-12 - migration.pdf")
    db.update_order_status(oid, "Envoyée")
    uid = db.get_order(oid)[1][0]["line_uid"]
    db.add_receipt(oid, date.today(), {uid: 7}, "BL migration")
    attachment = profile / "documents/bon-livraison.txt"
    attachment.write_text("Bon de livraison conservé", encoding="utf-8")
    db.add_order_attachment(
        oid, "Bon de livraison", attachment.name, str(attachment), True
    )
    with db.connect() as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 15
    expected = {
        "tables": snapshot(db),
        "files": {
            str(p.relative_to(profile)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (profile / "documents").rglob("*")
            if p.is_file()
        },
    }
    (profile / "upgrade-expected.json").write_text(
        json.dumps(expected, ensure_ascii=False), encoding="utf-8"
    )


def check(profile):
    from cahpp_app.database import Database

    db = Database(profile / "data/commandes_cahpp.sqlite3")
    expected = json.loads(
        (profile / "upgrade-expected.json").read_text(encoding="utf-8")
    )
    assert snapshot(db) == expected["tables"], (
        "Données métier modifiées pendant la migration"
    )
    for name, digest in expected["files"].items():
        assert hashlib.sha256((profile / name).read_bytes()).hexdigest() == digest, name
    with db.connect() as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 16
        assert c.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    print(
        "Migration bêta 5 → RC1 : commandes, réception, réglages, PDF et pièces jointes conservés."
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=Path)
    parser.add_argument("--check", type=Path)
    args = parser.parse_args()
    if args.seed:
        seed(args.seed.resolve())
    elif args.check:
        check(args.check.resolve())
    else:
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "profile"
            seed(profile)
            check(profile)


if __name__ == "__main__":
    main()
