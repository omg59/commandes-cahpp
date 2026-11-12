"""Cas d'usage Horizon : mêmes transactions et verrous que le moteur 1.6.

Le verrou de processus sérialise les synchronisations et les écritures locales.
Une action d'interface refuse une écriture pendant un travail réseau, sans
attendre dans le thread graphique. Les commandes en préparation restent
réservées jusqu'à leur fermeture ; une réservation perdue interdit la sauvegarde.
"""

from __future__ import annotations

import threading
import logging
import uuid
from contextlib import contextmanager, nullcontext
from datetime import date, datetime
from pathlib import Path

from ..collaboration import CollaborationManager, CollaborationError
from ..local_services import configure_shared_workspace
from ..app_logging import log_failure

logger = logging.getLogger(__name__)


class Operations:
    def __init__(self, database):
        self.database = database
        self.manager = None
        self.guard = threading.RLock()
        self.order_lock = None
        self.editing_order = None
        self.last_sync_result = None
        self.last_sync_error = ""
        self.held_resources = {}
        self.collaboration_requested = (
            database.get_settings().get("collaboration_enabled") == "1"
        )
        try:
            self.configure()
        except Exception as exc:
            self.last_sync_error = f"{type(exc).__name__}: {exc}"
            # La consultation et les diagnostics restent accessibles hors réseau.
            database.set_current_user(
                database.get_settings().get("user_id") or str(uuid.uuid4()),
                database.get_settings().get("user_name") or "Utilisateur Horizon",
            )

    def configure(self):
        settings = self.database.get_settings()
        actor = settings.get("user_id") or str(uuid.uuid4())
        name = settings.get("user_name") or "Utilisateur Horizon"
        manager = None
        if settings.get("collaboration_enabled") == "1":
            path = settings.get("shared_workspace_path", "").strip()
            if not path:
                raise ValueError(
                    "Choisissez un dossier partagé avant d'activer la collaboration."
                )
            manager = CollaborationManager(self.database, actor, name, path)
            manager.initialize_workspace()
        if self.manager:
            self.release_all()
        self.order_lock = None
        self.editing_order = None
        self.database.save_settings({"user_id": actor, "user_name": name})
        self.database.set_current_user(actor, name)
        self.manager = manager
        self.collaboration_requested = manager is not None
        self.last_sync_error = ""
        configure_shared_workspace(manager.root if manager else None)

    @contextmanager
    def write(self):
        if self.collaboration_requested and self.manager is None:
            raise ValueError(
                "Le partage configuré est indisponible. Rétablissez l'accès ou désactivez la collaboration dans les paramètres avant de modifier des données."
            )
        if not self.guard.acquire(blocking=False):
            raise ValueError(
                "Une synchronisation ou une maintenance est en cours. Réessayez à sa fin."
            )
        try:
            yield
        finally:
            self.guard.release()

    @contextmanager
    def resource(self, kind, key):
        with self.write():
            if kind == "fournisseur":
                supplier = self.database.get_supplier(key)
                if supplier is None:
                    raise ValueError("Fournisseur introuvable.")
                key = str(supplier["cahpp_id"] or supplier["name"]).strip().casefold()
            handle = None
            resource = f"{kind}:{key}"
            retained = (
                self.order_lock
                if kind == "commande"
                and self.order_lock
                and self.order_lock.resource == resource
                else self.held_resources.get(resource)
            )
            if self.manager:
                if retained:
                    if retained.released:
                        raise ValueError(
                            "Le verrou de cette commande a été perdu. Reprenez-la depuis l'historique."
                        )
                    retained.refresh()
                else:
                    handle = self.manager.acquire_lock(kind, str(key))
                    self.held_resources[resource] = handle
            try:
                if self.manager and kind == "commande":
                    self.manager.refresh_order(str(key))
                yield
                if self.manager and kind == "commande":
                    with self.database.connect() as c:
                        row = c.execute(
                            "SELECT id FROM orders WHERE shared_uid=? AND sync_state<>'Synchronisée'",
                            (str(key),),
                        ).fetchone()
                    if row:
                        self.manager.publish_order(row["id"])
            finally:
                if handle:
                    try:
                        self.release_handle(handle)
                    finally:
                        self.held_resources.pop(resource, None)

    def locked_order(self, order_id):
        order, _ = self.database.get_order(order_id)
        return self.resource("commande", order["shared_uid"])

    def locked_product(self, product_id):
        product = self.database.get_product(product_id)
        if product is None:
            raise ValueError("Article introuvable.")
        return self.resource("produit", product["code_cahpp"])

    def hold_order(self, order_id):
        if self.editing_order == order_id:
            if self.manager and (not self.order_lock or self.order_lock.released):
                raise ValueError(
                    "Verrou perdu. Fermez cette préparation avant de la reprendre."
                )
            return
        self.release_order()
        if self.manager:
            order, _ = self.database.get_order(order_id)
            self.order_lock = self.manager.acquire_lock("commande", order["shared_uid"])
            try:
                self.manager.refresh_order(order["shared_uid"])
            except Exception:
                self.release_handle(self.order_lock)
                self.order_lock = None
                raise
        self.editing_order = order_id

    def release_order(self):
        if self.order_lock:
            self.release_handle(self.order_lock)
        self.order_lock = None
        self.editing_order = None

    def release_handle(self, handle):
        try:
            handle.release()
        except (OSError, CollaborationError) as exc:
            self.last_sync_error = (
                f"Libération d'un verrou : {type(exc).__name__}: {exc}"
            )
            log_failure(logger, "horizon_liberation_verrou_echec", exc)

    def release_all(self):
        if self.manager:
            try:
                self.manager.release_all_locks()
            except (OSError, CollaborationError) as exc:
                self.last_sync_error = (
                    f"Libération des verrous : {type(exc).__name__}: {exc}"
                )
                log_failure(logger, "horizon_fermeture_verrous_echec", exc)

    def save_cart(self, cart, notes="", service="", selected_date=None):
        with self.write():
            if not cart.lines:
                raise ValueError("Ajoutez un article avant d'enregistrer.")
            if cart.order_id and self.manager:
                if (
                    self.editing_order != cart.order_id
                    or not self.order_lock
                    or self.order_lock.released
                ):
                    raise ValueError(
                        "La commande n'est plus réservée. Reprenez-la depuis l'historique."
                    )
                self.order_lock.refresh()
            number = (
                self.manager.reserve_order_number(selected_date)
                if self.manager and not cart.order_id
                else None
            )
            oid = self.database.save_order(
                cart.supplier_id,
                [line.as_mapping() for line in cart.lines],
                notes=notes,
                order_id=cart.order_id,
                requester_service=service,
                selected_date=selected_date,
                order_number=number,
            )
            cart.order_id = oid
            cart.dirty = False
            self.hold_order(oid)
            if self.manager:
                self.manager.publish_order(oid)
            return oid

    def duplicate(self, order_id, line_uids=None):
        with self.locked_order(order_id):
            number = self.manager.reserve_order_number() if self.manager else None
            if line_uids is None:
                return self.database.duplicate_order(order_id, order_number=number)
            return self.database.duplicate_order_lines(
                order_id, line_uids, order_number=number
            )

    def sync(self, *, cancel, progress):
        with self.guard:
            if cancel.is_set() or not self.manager:
                return {"enabled": False}
            try:
                self.manager.refresh_active_locks()
                self.retry_catalog_publication()
                result = self.manager.sync_all()
                self.last_sync_result, self.last_sync_error = result, ""
                return result
            except Exception as exc:
                self.last_sync_error = f"{type(exc).__name__}: {exc}"
                raise

    def import_catalog(
        self, path, preview, options, *, cancel, progress, shared_manifest=None
    ):
        from ..catalog_importer import CatalogImporter
        from ..local_services import create_complete_backup
        from ..paths import BACKUP_DIR

        with self.write():
            lock = (
                self.manager.acquire_lock("systeme", "catalogue", ttl_seconds=7200)
                if self.manager
                else nullcontext()
            )
            with lock as handle:
                if cancel.is_set():
                    raise ValueError("Import annulé.")
                if not preview.already_imported:
                    progress(0, 100, "Sauvegarde complète avant import…")
                    path_backup = BACKUP_DIR / (
                        "horizon-avant-import-"
                        + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                        + ".zip"
                    )
                    temp = path_backup.with_name("." + path_backup.name)
                    try:
                        create_complete_backup(self.database, temp)
                        temp.replace(path_backup)
                    except Exception:
                        temp.unlink(missing_ok=True)
                        raise
                if self.manager and not shared_manifest:
                    self.retry_catalog_publication(lock=handle)
                    self.queue_catalog_publication(Path(path))
                result = CatalogImporter(self.database).import_file(
                    path, options=options, preview=preview, progress=progress
                )
                if self.manager:
                    if shared_manifest:
                        self.manager.mark_catalog_applied(shared_manifest)
                    else:
                        self.retry_catalog_publication(lock=handle)
                return result

    def queue_catalog_publication(self, source):
        import json
        import shutil
        from ..catalog_import.formats import sha256

        pending = Path(self.database.path).parent / "catalogue-a-publier.xlsx"
        temporary = pending.with_suffix(".tmp")
        shutil.copy2(source, temporary)
        temporary.replace(pending)
        self.database.save_settings(
            {
                "horizon_catalog_pending": json.dumps(
                    {"path": str(pending), "file_hash": sha256(pending)}
                )
            }
        )

    def retry_catalog_publication(self, lock=None):
        import json
        from ..catalog_import.engine import _previous_result

        pending = self.database.get_settings().get("horizon_catalog_pending", "")
        if not pending or not self.manager:
            return
        record = json.loads(pending)
        with self.database.connect() as c:
            imported = c.execute(
                "SELECT * FROM imports WHERE file_hash=?", (record["file_hash"],)
            ).fetchone()
        if imported is None:
            return
        self.manager.publish_catalog(
            Path(record["path"]), _previous_result(imported), lock=lock
        )
        self.database.save_settings({"horizon_catalog_pending": ""})
        Path(record["path"]).unlink(missing_ok=True)

    def close(self):
        with self.guard:
            self.release_order()
            self.release_all()

    def pending_installer(self, current_version, dismissed=""):
        import re

        import sys

        if (
            sys.platform != "win32"
            or not self.manager
            or not self.manager.updates_dir.is_dir()
        ):
            return None

        def version_key(text):
            m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?", text)
            if not m:
                return None
            return (
                *map(int, m.group(1, 2, 3)),
                {"a": 0, "b": 1, "rc": 2, None: 3}[m.group(4)],
                int(m.group(5) or 0),
            )

        current = version_key(current_version)
        ignored = version_key(dismissed)
        candidates = []
        for path in self.manager.updates_dir.glob("CommandesCAHPP-Horizon-Setup-*.exe"):
            value = path.name.removeprefix(
                "CommandesCAHPP-Horizon-Setup-"
            ).removesuffix(".exe")
            key = version_key(value)
            if key and current and key > current and (ignored is None or key > ignored):
                candidates.append((key, value, path))
        if candidates:
            _, version, path = max(candidates)
            return {"version": version, "path": str(path)}


def months_before(value: date, months: int) -> date:
    import calendar

    serial = value.year * 12 + value.month - 1 - months
    year, month = serial // 12, serial % 12 + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))
