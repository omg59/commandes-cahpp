"""Cas d'usage Horizon : mêmes transactions et verrous que le moteur 1.6.

Le verrou de processus sérialise les synchronisations et les écritures locales.
Une action d'interface refuse une écriture pendant un travail réseau, sans
attendre dans le thread graphique. Les commandes en préparation restent
réservées jusqu'à leur fermeture ; une réservation perdue interdit la sauvegarde.
"""

from __future__ import annotations

import threading
import uuid
from contextlib import contextmanager, nullcontext
from datetime import date, datetime
from pathlib import Path

from ..collaboration import CollaborationManager
from ..local_services import configure_shared_workspace


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
            self.manager.release_all_locks()
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
                yield
            finally:
                if handle:
                    handle.release()
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
        self.editing_order = order_id

    def release_order(self):
        if self.order_lock:
            self.order_lock.release()
        self.order_lock = None
        self.editing_order = None

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

        with self.guard:
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
                result = CatalogImporter(self.database).import_file(
                    path, options=options, preview=preview, progress=progress
                )
                if self.manager:
                    if shared_manifest:
                        self.manager.mark_catalog_applied(shared_manifest)
                    elif not result.already_imported:
                        self.manager.publish_catalog(Path(path), result, lock=handle)
                return result

    def close(self):
        with self.guard:
            self.release_order()
            if self.manager:
                self.manager.release_all_locks()

    def pending_installer(self, current_version, dismissed=""):
        import re

        if not self.manager or not self.manager.updates_dir.is_dir():
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
