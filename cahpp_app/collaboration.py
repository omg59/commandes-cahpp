from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Mapping

from .database import Database


WORKSPACE_FORMAT = 1
TEAM_STATE_FORMAT = 1
ORDER_FORMAT = 1
LOCK_TTL_SECONDS = 180


class CollaborationError(RuntimeError):
    pass


class ResourceLockedError(CollaborationError):
    def __init__(self, resource: str, owner: str, expires_at: str):
        self.resource = resource
        self.owner = owner
        self.expires_at = expires_at
        super().__init__(
            f"Cette ressource est utilisée par {owner or 'un autre utilisateur'}."
        )


class SyncConflictError(CollaborationError):
    pass


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path, default: object | None = None):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CollaborationError(f"Fichier partagé illisible : {path.name}") from exc


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _record_key(record: Mapping[str, object] | None) -> tuple[str, str]:
    if not record:
        return "", ""
    return (
        str(record.get("updated_at") or ""),
        str(record.get("updated_by") or ""),
    )


def _safe_component(value: str) -> str:
    readable = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")[:45]
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{readable or 'resource'}-{digest}"


@dataclass
class WorkspaceTest:
    path: Path
    readable: bool
    writable: bool
    atomic_rename: bool
    workspace_found: bool
    workspace_id: str = ""

    @property
    def ok(self) -> bool:
        return self.readable and self.writable and self.atomic_rename


class ResourceLock:
    def __init__(
        self,
        manager: "CollaborationManager",
        resource: str,
        path: Path,
        token: str,
    ):
        self.manager = manager
        self.resource = resource
        self.path = path
        self.token = token
        self.released = False

    def refresh(self) -> None:
        if self.released:
            return
        payload = _read_json(self.path, {})
        if not isinstance(payload, dict) or payload.get("token") != self.token:
            self.released = True
            raise ResourceLockedError(self.resource, "", "")
        payload["heartbeat_at"] = _now()
        payload["expires_at"] = (
            datetime.now() + timedelta(seconds=LOCK_TTL_SECONDS)
        ).isoformat(timespec="seconds")
        _atomic_json(self.path, payload)

    def release(self) -> None:
        if self.released:
            return
        try:
            payload = _read_json(self.path, {})
            if isinstance(payload, dict) and payload.get("token") == self.token:
                self.path.unlink(missing_ok=True)
        finally:
            self.released = True
            self.manager._active_locks.pop(self.resource, None)

    def __enter__(self) -> "ResourceLock":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.release()


class CollaborationManager:
    def __init__(
        self,
        database: Database,
        user_id: str,
        user_name: str,
        root: str | Path | None,
    ):
        self.database = database
        self.user_id = user_id.strip()
        self.user_name = user_name.strip() or "Utilisateur"
        self.root = (
            Path(root).expanduser().resolve()
            if str(root or "").strip()
            else None
        )
        self.workspace_id = ""
        self._active_locks: dict[str, ResourceLock] = {}

    @property
    def enabled(self) -> bool:
        return self.root is not None

    @property
    def orders_dir(self) -> Path:
        return self._required_root() / "commandes"

    @property
    def catalogs_dir(self) -> Path:
        return self._required_root() / "catalogues"

    @property
    def documents_dir(self) -> Path:
        return self.orders_dir

    def _required_root(self) -> Path:
        if self.root is None:
            raise CollaborationError("Aucun dossier partagé n'est configuré.")
        return self.root

    @staticmethod
    def test_path(path: str | Path) -> WorkspaceTest:
        root = Path(path).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        readable = root.is_dir()
        writable = False
        atomic_rename = False
        probe = root / f".commandes-cahpp-test-{uuid.uuid4().hex}.tmp"
        renamed = probe.with_suffix(".ok")
        try:
            probe.write_text("test", encoding="utf-8")
            writable = probe.read_text(encoding="utf-8") == "test"
            os.replace(probe, renamed)
            atomic_rename = renamed.is_file()
        finally:
            probe.unlink(missing_ok=True)
            renamed.unlink(missing_ok=True)
        manifest = _read_json(root / "espace-collaboratif.json", {})
        return WorkspaceTest(
            path=root.resolve(),
            readable=readable,
            writable=writable,
            atomic_rename=atomic_rename,
            workspace_found=bool(manifest),
            workspace_id=(
                str(manifest.get("workspace_id") or "")
                if isinstance(manifest, dict)
                else ""
            ),
        )

    def initialize_workspace(self) -> str:
        root = self._required_root()
        tested = self.test_path(root)
        if not tested.ok:
            raise CollaborationError(
                "Le dossier partagé ne permet pas une synchronisation sûre."
            )
        manifest_path = root / "espace-collaboratif.json"
        manifest = _read_json(manifest_path, None)
        if manifest is None:
            manifest = {
                "application": "Commandes CAHPP",
                "format": WORKSPACE_FORMAT,
                "workspace_id": str(uuid.uuid4()),
                "created_at": _now(),
                "created_by": self.user_name,
            }
            _atomic_json(manifest_path, manifest)
        if not isinstance(manifest, dict) or int(manifest.get("format", 0)) != 1:
            raise CollaborationError(
                "Ce dossier ne contient pas un espace collaboratif compatible."
            )
        self.workspace_id = str(manifest.get("workspace_id") or "")
        for directory in (
            root / "verrous",
            root / "equipe" / "revisions",
            root / "commandes",
            root / "catalogues" / "versions",
        ):
            directory.mkdir(parents=True, exist_ok=True)
        self.database.save_settings(
            {
                "collaboration_enabled": "1",
                "shared_workspace_path": str(root),
                "collaboration_workspace_id": self.workspace_id,
            }
        )
        return self.workspace_id

    def acquire_lock(
        self, kind: str, key: str, ttl_seconds: int = LOCK_TTL_SECONDS
    ) -> ResourceLock:
        resource = f"{kind}:{key}"
        active = self._active_locks.get(resource)
        if active and not active.released:
            return active
        lock_path = (
            self._required_root()
            / "verrous"
            / kind
            / f"{_safe_component(key)}.lock"
        )
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        token = str(uuid.uuid4())
        expires = datetime.now() + timedelta(seconds=ttl_seconds)
        payload = {
            "format": 1,
            "resource": resource,
            "token": token,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "created_at": _now(),
            "heartbeat_at": _now(),
            "expires_at": expires.isoformat(timespec="seconds"),
        }
        for _ in range(2):
            try:
                descriptor = os.open(
                    lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    json.dump(payload, stream, ensure_ascii=False, indent=2)
                handle = ResourceLock(self, resource, lock_path, token)
                self._active_locks[resource] = handle
                return handle
            except FileExistsError:
                existing = _read_json(lock_path, {})
                expires_at = str(
                    existing.get("expires_at") or ""
                    if isinstance(existing, dict)
                    else ""
                )
                try:
                    expired = (
                        not expires_at
                        or datetime.fromisoformat(expires_at) < datetime.now()
                    )
                except ValueError:
                    expired = True
                if expired:
                    lock_path.unlink(missing_ok=True)
                    continue
                owner = (
                    str(existing.get("user_name") or "")
                    if isinstance(existing, dict)
                    else ""
                )
                raise ResourceLockedError(resource, owner, expires_at)
        raise CollaborationError("Le verrou partagé n'a pas pu être créé.")

    def refresh_active_locks(self) -> None:
        for handle in list(self._active_locks.values()):
            try:
                handle.refresh()
            except (CollaborationError, OSError):
                handle.released = True

    def release_all_locks(self) -> None:
        for handle in list(self._active_locks.values()):
            handle.release()

    def cleanup_expired_locks(self) -> int:
        root = self._required_root() / "verrous"
        if not root.is_dir():
            return 0
        removed = 0
        now = datetime.now()
        for path in root.glob("*/*.lock"):
            payload = _read_json(path, {})
            expires_at = (
                str(payload.get("expires_at") or "")
                if isinstance(payload, dict)
                else ""
            )
            try:
                expired = (
                    not expires_at
                    or datetime.fromisoformat(expires_at) < now
                )
            except ValueError:
                expired = True
            if not expired:
                continue
            # Relire juste avant la suppression : un poste a pu renouveler le
            # verrou depuis la première lecture.
            current = _read_json(path, {})
            current_expiry = (
                str(current.get("expires_at") or "")
                if isinstance(current, dict)
                else ""
            )
            try:
                still_expired = (
                    not current_expiry
                    or datetime.fromisoformat(current_expiry) < datetime.now()
                )
            except ValueError:
                still_expired = True
            if still_expired:
                path.unlink(missing_ok=True)
                removed += 1
        return removed

    def _merge_team_states(
        self,
        local: Mapping[str, object],
        remote: Mapping[str, object],
    ) -> dict[str, object]:
        merged: dict[str, object] = {
            "format": TEAM_STATE_FORMAT,
            "revision": int(remote.get("revision") or 0) + 1,
            "updated_at": _now(),
            "updated_by": self.user_name,
            "users": dict(remote.get("users") or {}),
        }
        users = dict(merged["users"])
        users[self.user_id] = {
            "user_id": self.user_id,
            "name": self.user_name,
            "updated_at": _now(),
            "updated_by": self.user_name,
        }
        merged["users"] = users
        for collection in (
            "suppliers",
            "preferences",
            "overrides",
            "manual_products",
        ):
            local_items = dict(local.get(collection) or {})
            remote_items = dict(remote.get(collection) or {})
            result: dict[str, object] = {}
            for key in local_items.keys() | remote_items.keys():
                local_record = local_items.get(key)
                remote_record = remote_items.get(key)
                if remote_record is None:
                    result[key] = local_record
                elif local_record is None:
                    result[key] = remote_record
                else:
                    result[key] = (
                        local_record
                        if _record_key(local_record)
                        > _record_key(remote_record)
                        else remote_record
                    )
            merged[collection] = result
        local_settings = dict(local.get("team_settings") or {})
        remote_settings = dict(remote.get("team_settings") or {})
        merged["team_settings"] = (
            local_settings
            if _record_key(local_settings) > _record_key(remote_settings)
            else remote_settings
        )
        return merged

    def sync_team_state(self) -> dict[str, int]:
        if not self.enabled:
            return {}
        with self.acquire_lock("systeme", "donnees-equipe", ttl_seconds=60):
            state_path = self._required_root() / "equipe" / "etat.json"
            remote = _read_json(state_path, {})
            if not isinstance(remote, dict):
                remote = {}
            local = self.database.export_team_state()
            merged = self._merge_team_states(local, remote)
            revision = int(merged.get("revision") or 1)
            revision_path = (
                self._required_root()
                / "equipe"
                / "revisions"
                / f"etat-{revision:06d}.json"
            )
            _atomic_json(revision_path, merged)
            _atomic_json(state_path, merged)
            result = self.database.apply_team_state(merged)
            self._trim_revisions(
                self._required_root() / "equipe" / "revisions",
                "etat-*.json",
                keep=20,
            )
            return result

    @staticmethod
    def _trim_revisions(directory: Path, pattern: str, keep: int) -> None:
        paths = sorted(directory.glob(pattern))
        for path in paths[:-keep]:
            path.unlink(missing_ok=True)

    def reserve_order_number(self, selected_date: date | None = None) -> str:
        selected_date = selected_date or date.today()
        year = str(selected_date.year)
        with self.acquire_lock("systeme", "numerotation", ttl_seconds=60):
            state_path = self._required_root() / "commandes" / "numerotation.json"
            state = _read_json(state_path, {})
            if not isinstance(state, dict):
                state = {}
            sequences = dict(state.get("sequences") or {})
            current = int(sequences.get(year) or 0)
            prefix = f"BC-{year}-"
            for order_file in self.orders_dir.glob("*/commande.json"):
                payload = _read_json(order_file, {})
                if not isinstance(payload, dict):
                    continue
                number = str(dict(payload.get("order") or {}).get("order_number") or "")
                if number.startswith(prefix):
                    try:
                        current = max(current, int(number.rsplit("-", 1)[1]))
                    except (IndexError, ValueError):
                        pass
            current += 1
            sequences[year] = current
            _atomic_json(
                state_path,
                {
                    "format": 1,
                    "sequences": sequences,
                    "updated_at": _now(),
                    "updated_by": self.user_name,
                },
            )
            return f"{prefix}{current:04d}"

    def _order_dir(self, shared_uid: str) -> Path:
        return self.orders_dir / shared_uid

    def to_shared_uri(self, path: Path) -> str:
        relative = path.resolve().relative_to(self._required_root().resolve())
        return "shared:" + relative.as_posix()

    def resolve_shared_uri(self, value: str) -> Path:
        if not value.startswith("shared:"):
            return Path(value)
        relative = Path(value.removeprefix("shared:"))
        candidate = (self._required_root() / relative).resolve()
        candidate.relative_to(self._required_root().resolve())
        return candidate

    def _copy_order_files(
        self, order_id: int, payload: dict[str, object]
    ) -> dict[str, object]:
        from .local_services import resolve_portable_path, safe_filename

        order = dict(payload.get("order") or {})
        shared_uid = str(order["shared_uid"])
        files_dir = self._order_dir(shared_uid) / "fichiers"
        files_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = str(order.get("pdf_path") or "")
        shared_pdf = None
        if pdf_path:
            source = resolve_portable_path(pdf_path)
            if source.is_file():
                destination = files_dir / safe_filename(source.name)
                if source.resolve() != destination.resolve():
                    shutil.copy2(source, destination)
                shared_pdf = self.to_shared_uri(destination)
                order["pdf_path"] = shared_pdf
        attachment_paths: dict[str, str] = {}
        attachments = []
        for raw in list(payload.get("attachments") or []):
            item = dict(raw)
            source = resolve_portable_path(str(item.get("stored_path") or ""))
            if source.is_file():
                destination = files_dir / safe_filename(source.name)
                if source.resolve() != destination.resolve():
                    shutil.copy2(source, destination)
                shared_path = self.to_shared_uri(destination)
                item["stored_path"] = shared_path
                attachment_paths[str(item.get("display_name") or source.name)] = (
                    shared_path
                )
            attachments.append(item)
        payload["order"] = order
        payload["attachments"] = attachments
        return payload

    def _cache_order_files(
        self, payload: dict[str, object]
    ) -> dict[str, object]:
        from . import local_services
        from .local_services import portable_path, safe_filename

        cached = json.loads(json.dumps(payload))
        order = dict(cached.get("order") or {})
        shared_uid = str(order.get("shared_uid") or "")
        if not shared_uid:
            return cached
        cache_dir = local_services.DOCUMENTS_DIR / "_partage" / shared_uid
        cache_dir.mkdir(parents=True, exist_ok=True)

        pdf_path = str(order.get("pdf_path") or "")
        if pdf_path.startswith("shared:"):
            source = self.resolve_shared_uri(pdf_path)
            if source.is_file():
                destination = cache_dir / safe_filename(source.name)
                if source.resolve() != destination.resolve():
                    shutil.copy2(source, destination)
                order["pdf_path"] = portable_path(destination)

        attachments = []
        for raw in list(cached.get("attachments") or []):
            item = dict(raw)
            stored_path = str(item.get("stored_path") or "")
            if stored_path.startswith("shared:"):
                source = self.resolve_shared_uri(stored_path)
                if source.is_file():
                    destination = cache_dir / safe_filename(source.name)
                    if source.resolve() != destination.resolve():
                        shutil.copy2(source, destination)
                    item["stored_path"] = portable_path(destination)
            attachments.append(item)
        cached["order"] = order
        cached["attachments"] = attachments
        return cached

    def publish_order(self, order_id: int) -> None:
        if not self.enabled:
            return
        payload = self.database.export_order(order_id)
        order = dict(payload.get("order") or {})
        shared_uid = str(order.get("shared_uid") or "")
        if not shared_uid:
            raise CollaborationError("La commande ne possède pas d'identifiant partagé.")
        resource = f"commande:{shared_uid}"
        own_lock = resource not in self._active_locks
        handle = (
            self.acquire_lock("commande", shared_uid)
            if own_lock
            else self._active_locks[resource]
        )
        try:
            order_dir = self._order_dir(shared_uid)
            order_dir.mkdir(parents=True, exist_ok=True)
            current_path = order_dir / "commande.json"
            remote = _read_json(current_path, {})
            if isinstance(remote, dict) and remote:
                remote_order = dict(remote.get("order") or {})
                remote_revision = int(remote_order.get("shared_revision") or 0)
                local_revision = int(order.get("shared_revision") or 0)
                if remote_revision > local_revision:
                    raise SyncConflictError(
                        "Une version plus récente de cette commande existe "
                        "sur le partage."
                    )
                if (
                    remote_revision == local_revision
                    and str(remote_order.get("updated_at") or "")
                    > str(order.get("updated_at") or "")
                ):
                    raise SyncConflictError(
                        "Cette commande a été modifiée sur un autre poste."
                    )
            payload = self._copy_order_files(order_id, dict(payload))
            order = dict(payload["order"])
            revision = int(order.get("shared_revision") or 1)
            revisions = order_dir / "revisions"
            revisions.mkdir(parents=True, exist_ok=True)
            _atomic_json(
                revisions / f"commande-{revision:06d}.json",
                payload,
            )
            _atomic_json(current_path, payload)
            self._trim_revisions(revisions, "commande-*.json", keep=30)
            cached = self._cache_order_files(payload)
            cached_order = dict(cached.get("order") or {})
            cached_attachments = {
                str(item.get("display_name") or ""): str(
                    item.get("stored_path") or ""
                )
                for item in list(cached.get("attachments") or [])
            }
            self.database.update_order_shared_paths(
                order_id,
                pdf_path=str(cached_order.get("pdf_path") or ""),
                attachment_paths=cached_attachments,
            )
            self.database.mark_order_synced(order_id)
        finally:
            if own_lock:
                handle.release()

    def sync_orders(self) -> dict[str, int]:
        if not self.enabled:
            return {"imported": 0, "published": 0, "conflicts": 0}
        imported = 0
        published = 0
        conflicts = 0
        for path in sorted(self.orders_dir.glob("*/commande.json")):
            payload = _read_json(path, {})
            if not isinstance(payload, dict):
                continue
            cached = self._cache_order_files(payload)
            _, changed = self.database.import_order(cached)
            imported += int(changed)
        for order_id in self.database.pending_order_ids():
            try:
                self.publish_order(order_id)
                published += 1
            except (ResourceLockedError, SyncConflictError):
                conflicts += 1
        return {
            "imported": imported,
            "published": published,
            "conflicts": conflicts,
        }

    def publish_catalog(self, source: Path, result) -> dict[str, object]:
        if not self.enabled:
            return {}
        source = Path(source)
        if not source.is_file():
            raise FileNotFoundError(source)
        file_hash = _sha256(source)
        with self.acquire_lock("systeme", "catalogue", ttl_seconds=600):
            current_path = self.catalogs_dir / "catalogue-actuel.json"
            current = _read_json(current_path, {})
            if isinstance(current, dict) and current.get("sha256") == file_hash:
                self.database.save_settings(
                    {
                        "collaboration_catalog_hash": file_hash,
                        "collaboration_catalog_version": current.get(
                            "version", ""
                        ),
                    }
                )
                return current
            version = (
                datetime.now().strftime("%Y-%m-%d_%H%M%S")
                + "-"
                + file_hash[:10]
            )
            versions = self.catalogs_dir / "versions"
            versions.mkdir(parents=True, exist_ok=True)
            destination = versions / version
            incoming = versions / f".incoming-{uuid.uuid4().hex}"
            incoming.mkdir()
            catalog_path = incoming / "catalogue.xlsx"
            try:
                shutil.copy2(source, catalog_path)
                if _sha256(catalog_path) != file_hash:
                    raise CollaborationError(
                        "La copie du catalogue partagé n'est pas intègre."
                    )
                manifest = {
                    "format": 1,
                    "version": version,
                    "sha256": file_hash,
                    "source_name": source.name,
                    "published_at": _now(),
                    "published_by": self.user_name,
                    "row_count": int(getattr(result, "row_count", 0)),
                    "added_count": int(getattr(result, "added_count", 0)),
                    "updated_count": int(getattr(result, "updated_count", 0)),
                    "missing_count": int(getattr(result, "missing_count", 0)),
                    "relative_path": f"versions/{version}/catalogue.xlsx",
                }
                _atomic_json(incoming / "manifest.json", manifest)
                if destination.exists():
                    shutil.rmtree(incoming)
                else:
                    os.replace(incoming, destination)
                _atomic_json(current_path, manifest)
            except Exception:
                if incoming.exists():
                    shutil.rmtree(incoming)
                raise
            self.database.save_settings(
                {
                    "collaboration_catalog_hash": file_hash,
                    "collaboration_catalog_version": version,
                }
            )
            return manifest

    def pending_catalog(self) -> dict[str, object] | None:
        if not self.enabled:
            return None
        current = _read_json(
            self.catalogs_dir / "catalogue-actuel.json", None
        )
        if not isinstance(current, dict):
            return None
        settings = self.database.get_settings()
        if current.get("sha256") == settings.get(
            "collaboration_catalog_hash", ""
        ):
            return None
        return current

    def catalog_source(self, manifest: Mapping[str, object]) -> Path:
        relative = str(manifest.get("relative_path") or "")
        path = (self.catalogs_dir / relative).resolve()
        path.relative_to(self.catalogs_dir.resolve())
        if not path.is_file():
            raise CollaborationError("Le catalogue partagé est introuvable.")
        expected = str(manifest.get("sha256") or "")
        if not expected or _sha256(path) != expected:
            raise CollaborationError(
                "Le catalogue partagé est incomplet ou endommagé."
            )
        return path

    def mark_catalog_applied(self, manifest: Mapping[str, object]) -> None:
        self.database.save_settings(
            {
                "collaboration_catalog_hash": str(
                    manifest.get("sha256") or ""
                ),
                "collaboration_catalog_version": str(
                    manifest.get("version") or ""
                ),
            }
        )

    def sync_all(self) -> dict[str, object]:
        if not self.enabled:
            return {"enabled": False}
        self.initialize_workspace()
        cleaned_locks = self.cleanup_expired_locks()
        team = self.sync_team_state()
        orders = self.sync_orders()
        self.database.save_settings({"collaboration_last_sync_at": _now()})
        return {
            "enabled": True,
            "team": team,
            "orders": orders,
            "cleaned_locks": cleaned_locks,
            "catalog_pending": bool(self.pending_catalog()),
            "synced_at": _now(),
        }

    def diagnostic_snapshot(self) -> dict[str, object]:
        root = self._required_root()
        tested = self.test_path(root)
        manifest = _read_json(root / "espace-collaboratif.json", {})
        team_state = _read_json(root / "equipe" / "etat.json", {})
        catalog = _read_json(
            root / "catalogues" / "catalogue-actuel.json", {}
        )
        now = datetime.now()
        active_locks = 0
        expired_locks = 0
        lock_owners: set[str] = set()
        for path in (root / "verrous").glob("*/*.lock"):
            payload = _read_json(path, {})
            if not isinstance(payload, dict):
                expired_locks += 1
                continue
            expires_at = str(payload.get("expires_at") or "")
            try:
                expired = (
                    not expires_at
                    or datetime.fromisoformat(expires_at) < now
                )
            except ValueError:
                expired = True
            if expired:
                expired_locks += 1
            else:
                active_locks += 1
                owner = str(payload.get("user_name") or "").strip()
                if owner:
                    lock_owners.add(owner)

        shared_orders = sum(
            1 for _ in (root / "commandes").glob("*/commande.json")
        )
        catalog_path = None
        catalog_integrity = None
        if isinstance(catalog, dict) and catalog.get("relative_path"):
            try:
                catalog_path = self.catalog_source(catalog)
                catalog_integrity = True
            except (OSError, CollaborationError, ValueError):
                catalog_integrity = False

        manifest_workspace_id = (
            str(manifest.get("workspace_id") or "")
            if isinstance(manifest, dict)
            else ""
        )
        return {
            "path": str(root),
            "readable": tested.readable,
            "writable": tested.writable,
            "atomic_rename": tested.atomic_rename,
            "workspace_id": manifest_workspace_id,
            "workspace_matches": bool(
                manifest_workspace_id
                and manifest_workspace_id == self.workspace_id
            ),
            "shared_orders": shared_orders,
            "team_revision": (
                int(team_state.get("revision") or 0)
                if isinstance(team_state, dict)
                else 0
            ),
            "catalog_version": (
                str(catalog.get("version") or "")
                if isinstance(catalog, dict)
                else ""
            ),
            "catalog_integrity": catalog_integrity,
            "catalog_path": str(catalog_path) if catalog_path else "",
            "active_locks": active_locks,
            "expired_locks": expired_locks,
            "lock_owners": sorted(lock_owners),
        }
