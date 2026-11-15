"""Projection du catalogue par blocs immuables, invalidée sur changement métier."""
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from ..database import PRODUCT_SELECT


def supplier_key(row):
    return "cahpp-" + str(row["cahpp_id"]) if row["cahpp_id"] else "nom-" + hashlib.sha256(row["name"].encode()).hexdigest()


def product_snapshot(db, product, supplier):
    record = {
        "code": product["code_cahpp"], "reference": product["supplier_ref"],
        "label": product["designation"], "supplier_id": supplier_key(supplier),
        "supplier": supplier["name"], "pack": product["conditionnement"] or product["qml"],
        "price": product["unit_price"], "vat": product["vat"],
        "review": bool(product["catalog_review_required"]), "active": bool(product["active"]),
    }
    record["fingerprint"] = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
    record["favorite"] = bool(product["favorite"])
    return record


def catalog_cache(db):
    root = db.path.parent / "mobile-catalog"
    meta = root / "manifest.json"
    with db.connect() as c:
        c.execute("BEGIN")
        revision = c.execute("SELECT revision FROM mobile_catalog_clock WHERE id=1").fetchone()[0]
        if meta.is_file():
            current = json.loads(meta.read_text())
            if current["revision"] == revision:
                return root, current
        suppliers = {r["id"]: dict(r) for r in c.execute("SELECT * FROM suppliers")}
        public_suppliers = [{
            k: s[k] for k in ("name", "email", "phone", "contact_name", "customer_number", "address",
                              "website", "franco_ht", "minimum_order_ht", "notes")
        } | {"id": supplier_key(s)} for s in sorted(suppliers.values(), key=lambda s: supplier_key(s))]
        incoming = Path(tempfile.mkdtemp(prefix="mobile-catalog-", dir=db.path.parent))
        try:
            digest = hashlib.sha256(json.dumps(public_suppliers, sort_keys=True).encode())
            batch, count, parts = [], 0, 0
            rows = c.execute(f"SELECT {PRODUCT_SELECT} FROM products p LEFT JOIN product_overrides po ON po.product_id=p.id WHERE p.active=1 ORDER BY p.code_cahpp")
            def flush():
                nonlocal parts
                data = json.dumps(batch, sort_keys=True)
                digest.update(data.encode())
                (incoming / f"{parts}.json").write_text(data)
                parts += 1
                batch.clear()
            for row in rows:
                p = db._effective_product(row)
                supplier = suppliers.get(p["supplier_id"])
                if supplier is None:
                    continue
                batch.append(product_snapshot(db, p, supplier))
                count += 1
                if len(batch) == 2000:
                    flush()
            if batch:
                flush()
            current = {"revision": revision, "generation": digest.hexdigest(), "count": count,
                       "parts": parts, "suppliers": public_suppliers}
            (incoming / "manifest.json").write_text(json.dumps(current))
            if root.exists():
                shutil.rmtree(root)
            os.replace(incoming, root)
            return root, current
        finally:
            if incoming.exists():
                shutil.rmtree(incoming)


def publish_catalog(db, relay):
    state = relay.call("mobile-state")
    root, manifest = catalog_cache(db)
    generation = manifest["generation"]
    if state["catalog"] == generation:
        return ""
    route = "catalog-sync/" + generation
    relay.call(route, {**manifest, "previous": state["catalog"]})
    received = set(relay.call(route)["parts"])
    missing = [i for i in range(manifest["parts"]) if i not in received]
    for part in missing[:25]:
        relay.call(route + "/" + str(part), json.loads((root / f"{part}.json").read_text()))
    done = len(received) + min(25, len(missing))
    if done == manifest["parts"]:
        relay.call(route + "/commit", {})
        return f"Catalogue mobile publié ({manifest['count']} références)."
    return f"Publication du catalogue mobile : {done}/{manifest['parts']} blocs."
