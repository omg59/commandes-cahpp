"""Projection du catalogue par blocs immuables, invalidée sur changement métier."""
import hashlib
import json
import math

from ..numbers import parse_decimal
from ..money_storage import decimal_text
import os
import shutil
import tempfile
import time
from pathlib import Path
from urllib.error import URLError

from ..database import PRODUCT_SELECT
from ..file_lock import FileLockBusy, exclusive_file
import re


class CatalogTransferPaused(ValueError):
    pass


def numeric(value):
    if value is None:
        return None
    try:
        number = float(parse_decimal(value, "Valeur du catalogue"))
        return number if math.isfinite(number) else None
    except (ValueError, OverflowError):
        return None


def supplier_key(row):
    return "cahpp-" + str(row["cahpp_id"]) if row["cahpp_id"] else "nom-" + hashlib.sha256(row["name"].encode()).hexdigest()


def product_snapshot(db, product, supplier, *, legacy_price=False):
    price = product["unit_price"]
    record = {
        "code": product["code_cahpp"], "reference": product["supplier_ref"],
        "label": product["designation"], "supplier_id": supplier_key(supplier),
        "supplier": supplier["name"], "pack": numeric(product["conditionnement"] or product["qml"]),
        "price": numeric(price) if legacy_price else decimal_text(price), "vat": numeric(product["vat"]),
        "review": bool(product["catalog_review_required"]), "active": bool(product["active"]),
    }
    record["fingerprint"] = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
    record["favorite"] = bool(product["favorite"])
    return record


def _cache_guard(db):
    return exclusive_file(db.path.parent / "mobile-catalog" / ".cache.guard")


def prune_catalog_cache(root, active):
    generations = sorted((p for p in root.iterdir() if p.is_dir() and not p.is_symlink()
                          and re.fullmatch("[a-f0-9]{64}", p.name)), key=lambda p: p.stat().st_mtime, reverse=True)
    keep = {active}
    previous = next((p.name for p in generations if p.name != active), None)
    if previous:
        keep.add(previous)
    for path in generations:
        if path.name not in keep:
            shutil.rmtree(path)
    cutoff = time.time() - 86400
    for path in root.glob("incoming-*"):
        if path.is_dir() and not path.is_symlink() and path.stat().st_mtime < cutoff:
            shutil.rmtree(path)


def catalog_cache(db):
    with _cache_guard(db):
        return _catalog_cache(db)


def _catalog_cache(db):
    root = db.path.parent / "mobile-catalog"
    root.mkdir(parents=True, exist_ok=True)
    meta = root / "manifest.json"
    with db.connect() as c:
        c.execute("BEGIN")
        revision = c.execute("SELECT revision FROM mobile_catalog_clock WHERE id=1").fetchone()[0]
        if meta.is_file():
            current = json.loads(meta.read_text())
            if current["revision"] == revision and (root / current["generation"]).is_dir():
                prune_catalog_cache(root, current["generation"])
                return root / current["generation"], current
        suppliers = {r["id"]: dict(r) for r in c.execute("SELECT * FROM suppliers")}
        public_suppliers = [{
            k: s[k] for k in ("name", "email", "phone", "contact_name", "customer_number", "address",
                              "website", "franco_ht", "minimum_order_ht", "notes")
        } | {"id": supplier_key(s), "franco_ht": decimal_text(s["franco_ht"]), "minimum_order_ht": decimal_text(s["minimum_order_ht"])} for s in sorted(suppliers.values(), key=lambda s: supplier_key(s))]
        incoming = Path(tempfile.mkdtemp(prefix="incoming-", dir=root))
        index = None
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
            destination = root / current["generation"]
            try:
                incoming.rename(destination)
            except OSError:
                if not destination.is_dir():
                    raise
            with tempfile.NamedTemporaryFile(mode="w", dir=root, suffix=".json", delete=False) as stream:
                json.dump(current, stream)
                index = Path(stream.name)
            os.replace(index, meta)
            prune_catalog_cache(root, current["generation"])
            return destination, current
        finally:
            if index is not None:
                index.unlink(missing_ok=True)
            if incoming.exists():
                shutil.rmtree(incoming)


def publish_catalog(db, relay):
    try:
        with _cache_guard(db):
            return _publish_catalog(db, relay)
    except FileLockBusy as exc:
        raise CatalogTransferPaused("Une autre publication utilise le cache du catalogue. Reprise au prochain cycle.") from exc


def _publish_catalog(db, relay):
    state = relay.call("mobile-state")
    relay.catalog_gzip = state.get("catalog_gzip", False) is True
    root, manifest = catalog_cache(db)
    generation = manifest["generation"]
    if state["catalog"] == generation:
        return ""
    route = "catalog-sync/" + generation
    done = None
    def paused_message(prefix):
        progress = (f"{done}/{manifest['parts']} blocs confirmés" if done is not None
                    else "progression à vérifier")
        return (f"{prefix} : {progress}. "
                "Reprise au prochain cycle ; les blocs reçus sont conservés.")

    def call(endpoint, body=None):
        try:
            return relay.call(endpoint, body)
        except (URLError, TimeoutError, ConnectionError) as exc:
            raise CatalogTransferPaused(paused_message("Publication du catalogue mobile interrompue")) from exc
        except ValueError as exc:
            if getattr(exc, "http_status", None) not in {408, 429, 500, 502, 503, 504, 507}:
                raise
            raise CatalogTransferPaused(paused_message("Relais temporairement indisponible")) from exc
    # La lecture des accusés précède le manifeste : même un échec d’envoi garde une progression exacte.
    received = set(call(route)["parts"])
    done = len(received)
    call(route, {**manifest, "previous": state["catalog"]})
    missing = [i for i in range(manifest["parts"]) if i not in received]
    started = time.monotonic()
    for part in missing[:25]:
        call(route + "/" + str(part), json.loads((root / f"{part}.json").read_text()))
        done += 1
        if time.monotonic() - started >= 20:
            break
    if done == manifest["parts"]:
        call(route + "/commit", {})
        return f"Catalogue mobile publié ({manifest['count']} références)."
    return f"Publication du catalogue mobile : {done}/{manifest['parts']} blocs."
