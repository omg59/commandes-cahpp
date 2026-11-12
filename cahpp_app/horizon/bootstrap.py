"""Profils de travail ; ce module n'importe ni Qt ni les chemins métier."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
import uuid
import shutil
from contextlib import closing
from datetime import datetime
from pathlib import Path

MARKER = "horizon-profile.json"
DATABASE_NAME = "commandes_cahpp.sqlite3"
ACTIVE_PROFILE = "profil-actif.json"


class StartupCancelled(Exception):
    """L'utilisateur a fermé le choix initial sans ouvrir de profil."""


def resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def data_root() -> Path:
    override = os.environ.get("CAHPP_HORIZON_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    return (
        Path(base) if base else Path.home() / ".local" / "share"
    ) / "CommandesCAHPP-Horizon"


def profile_launch_command(arguments):
    """Une nouvelle fenêtre AppImage doit conserver son propre montage vivant."""
    if not getattr(sys, "frozen", False):
        return sys.executable, [str(resource_root() / "main_horizon.py"), *arguments]
    appimage = os.environ.get("APPIMAGE", "")
    if sys.platform == "linux" and appimage and Path(appimage).is_file():
        return str(Path(appimage).resolve()), list(arguments)
    return sys.executable, list(arguments)


def profile_info(path: Path) -> dict:
    marker = path / MARKER
    if not marker.is_file():
        raise ValueError(
            "Ce dossier n'est pas un profil Horizon. Choisissez un profil existant ou un dossier vide."
        )
    info = json.loads(marker.read_text(encoding="utf-8"))
    if (
        not isinstance(info, dict)
        or info.get("application") != "commandes-cahpp-horizon"
        or info.get("format") != 1
    ):
        raise ValueError("Profil Horizon non reconnu.")
    return info


def initialize_profile(
    path: Path, *, mode="work", display_name="", user_name=""
) -> dict:
    path = path.expanduser().resolve()
    if (path / MARKER).exists():
        return profile_info(path)
    if path.exists() and any(path.iterdir()):
        raise ValueError(
            "Ce dossier contient déjà des fichiers. Pour reprendre une installation CAHPP, utilisez l'import d'une base existante."
        )
    path.mkdir(parents=True, exist_ok=True)
    info = {
        "application": "commandes-cahpp-horizon",
        "format": 1,
        "mode": mode,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "display_name": display_name or path.name,
        "initial_user_name": user_name,
    }
    (path / MARKER).write_text(json.dumps(info, indent=2), encoding="utf-8")
    return info


def remember_profile(path: Path):
    profile_info(path)
    root = data_root()
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / (ACTIVE_PROFILE + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(
            json.dumps({"format": 1, "path": str(path.resolve())}, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(root / ACTIVE_PROFILE)
    finally:
        temporary.unlink(missing_ok=True)


def validate_profile_database(path: Path):
    db = path / "data" / DATABASE_NAME
    if not db.is_file():
        raise ValueError(
            "Ce profil ne contient pas de base de données. Choisissez son dossier complet."
        )
    try:
        with closing(
            sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
        ) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            tables = {
                r[0]
                for r in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if (
                not 1 <= version <= 16
                or not {"products", "orders", "order_lines", "settings", "suppliers"}
                <= tables
            ):
                raise ValueError(
                    "Cette base n'est pas compatible avec cette version de Commandes CAHPP."
                )
    except sqlite3.Error as exc:
        raise ValueError(
            "La base de ce profil n'est pas une base CAHPP lisible."
        ) from exc


def remembered_profile():
    state = data_root() / ACTIVE_PROFILE
    if not state.is_file():
        return None
    try:
        value = json.loads(state.read_text(encoding="utf-8"))
        if (
            not isinstance(value, dict)
            or value.get("format") != 1
            or not value.get("path")
        ):
            raise ValueError("Sélection de profil non reconnue.")
        path = Path(value["path"]).expanduser().resolve()
        profile_info(path)
        validate_profile_database(path)
        return path
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError(
            "Le dernier profil est introuvable ou inaccessible. Choisissez à nouveau votre dossier de travail."
        ) from exc


def available_profiles():
    root = data_root()
    candidates = [root / "principal", *sorted((root / "profils").glob("*/"))]
    try:
        previous = remembered_profile()
        if previous:
            candidates.insert(0, previous)
    except ValueError:
        pass
    profiles = []
    for path in dict.fromkeys(candidates):
        try:
            info = profile_info(path)
        except (OSError, ValueError):
            continue
        # Les anciennes bases d'exemple restent sur disque ; elles ne sont
        # jamais proposées comme base de travail par défaut.
        if info.get("mode") == "demo":
            continue
        name = info.get("display_name") or path.name
        db = path / "data" / DATABASE_NAME
        if not db.is_file():
            continue
        if db.is_file():
            try:
                with closing(
                    sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
                ) as connection:
                    row = connection.execute(
                        "SELECT value FROM settings WHERE key='establishment_name'"
                    ).fetchone()
                    if row and row[0]:
                        name = row[0]
            except sqlite3.Error:
                pass
        profiles.append((path, name))
    return profiles


def copy_database(source: Path, profiles: Path) -> Path:
    """Copie cohérente (y compris WAL), source ouverte en lecture seule."""
    source = source.expanduser().resolve()
    if not source.is_file():
        raise ValueError("La base sélectionnée est introuvable.")
    profiles.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix="copie-", dir=profiles))
    initialize_profile(destination, mode="copy")
    target = destination / "data" / DATABASE_NAME
    target.parent.mkdir()
    try:
        origin = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=30)
        try:
            version = origin.execute("PRAGMA user_version").fetchone()[0]
            tables = {
                row[0]
                for row in origin.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if (
                not {"products", "orders", "order_lines", "settings", "suppliers"}
                <= tables
                or not 1 <= version <= 16
            ):
                raise ValueError(
                    "Choisissez une base Commandes CAHPP de schéma 16 ou antérieur."
                )
            with closing(sqlite3.connect(target)) as local, local:
                origin.backup(local)
                if local.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError("Le contrôle d'intégrité de la copie a échoué.")
                local.execute(
                    "UPDATE settings SET value='0' WHERE key='collaboration_enabled'"
                )
                local.execute(
                    "UPDATE settings SET value='' WHERE key IN ('collaboration_root','shared_folder','shared_workspace_path','collaboration_workspace_id','collaboration_last_sync_at','collaboration_catalog_hash','collaboration_catalog_version','horizon_catalog_pending','pdf_default_directory')"
                )
                local.execute(
                    "UPDATE settings SET value=? WHERE key='user_id'",
                    (str(uuid.uuid4()),),
                )
                source_root = (
                    source.parent.parent
                    if source.parent.name == "data"
                    else source.parent
                )
                copied_files = 0
                missing_files = 0

                def copy_file(value):
                    nonlocal copied_files, missing_files
                    if not value:
                        return ""
                    # Les références partagées sont récupérées seulement si le
                    # dossier de partage du profil source est accessible.
                    if value.startswith("shared:"):
                        row = origin.execute(
                            "SELECT value FROM settings WHERE key='shared_workspace_path'"
                        ).fetchone()
                        if not row or not row[0]:
                            missing_files += 1
                            return ""
                        base = Path(row[0]).expanduser().resolve()
                        original = (base / value.removeprefix("shared:")).resolve()
                        original.relative_to(base)
                    else:
                        original = Path(value).expanduser()
                        if not original.is_absolute():
                            original = source_root / original
                    if not original.is_file():
                        missing_files += 1
                        return ""
                    relative = (
                        Path("documents")
                        / "copie-initiale"
                        / uuid.uuid4().hex
                        / original.name
                    )
                    new_file = destination / relative
                    new_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(original, new_file)
                    copied_files += 1
                    return relative.as_posix()

                for oid, pdf in local.execute(
                    "SELECT id,pdf_path FROM orders"
                ).fetchall():
                    local.execute(
                        "UPDATE orders SET pdf_path=? WHERE id=?", (copy_file(pdf), oid)
                    )
                if "order_attachments" in tables:
                    for aid, stored in local.execute(
                        "SELECT id,stored_path FROM order_attachments"
                    ).fetchall():
                        local.execute(
                            "UPDATE order_attachments SET stored_path=? WHERE id=?",
                            (copy_file(stored), aid),
                        )
                logo = local.execute(
                    "SELECT value FROM settings WHERE key='logo_path'"
                ).fetchone()
                if logo and logo[0]:
                    local.execute(
                        "UPDATE settings SET value=? WHERE key='logo_path'",
                        (copy_file(logo[0]),),
                    )
                marker_info = profile_info(destination)
                marker_info.update(
                    {"copied_files": copied_files, "missing_files": missing_files}
                )
                (destination / MARKER).write_text(
                    json.dumps(marker_info, indent=2), encoding="utf-8"
                )
        finally:
            origin.close()
    except Exception as exc:
        # Supprimer seulement les fichiers de cette nouvelle copie incomplète.
        shutil.rmtree(destination)
        if isinstance(exc, sqlite3.Error):
            raise ValueError(
                "Le fichier sélectionné n'est pas une base CAHPP lisible."
            ) from exc
        raise
    return destination


def configure(argv=None, *, select_profile=None) -> tuple[Path, dict]:
    parser = argparse.ArgumentParser(
        description="Commandes CAHPP Horizon : ouvrir un profil de travail"
    )
    parser.add_argument(
        "--profile", type=Path, help="Profil Horizon existant ou dossier vide"
    )
    parser.add_argument(
        "--choose-profile", action="store_true", help="Choisir un profil de travail"
    )
    parser.add_argument(
        "--copy-database", type=Path, help="Créer une copie isolée d'une base CAHPP"
    )
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if (
        sum(
            bool(value)
            for value in (args.profile, args.copy_database, args.choose_profile)
        )
        > 1
    ):
        parser.error(
            "Choisir un profil, une base à importer ou le sélecteur de profil."
        )
    if args.copy_database:
        path = copy_database(args.copy_database, data_root() / "profils")
        info = profile_info(path)
    elif args.profile:
        path = args.profile
        info = initialize_profile(path)
        if (path / "data" / DATABASE_NAME).exists():
            validate_profile_database(path)
    else:
        previous_error = ""
        try:
            path = None if args.choose_profile else remembered_profile()
        except ValueError as exc:
            if select_profile is None:
                raise
            path, previous_error = None, str(exc)
        if path is not None:
            info = profile_info(path)
        elif select_profile is not None and not args.smoke_test:
            selection = select_profile(previous_error)
            if selection is None:
                raise StartupCancelled()
            if selection["action"] == "copy":
                path = copy_database(Path(selection["path"]), data_root() / "profils")
                info = profile_info(path)
            elif selection["action"] == "open":
                path = Path(selection["path"])
                info = profile_info(path)
                validate_profile_database(path)
            elif selection["action"] == "create":
                path = data_root() / "profils" / ("profil-" + uuid.uuid4().hex[:12])
                info = initialize_profile(
                    path,
                    display_name=selection["name"],
                    user_name=selection["user_name"],
                )
            else:
                raise ValueError("Choix de profil non reconnu.")
        else:
            path = data_root() / "principal"
            info = initialize_profile(path, display_name="Principal")
    remember_profile(path)
    os.environ["CAHPP_PORTABLE_ROOT"] = str(path.resolve())
    os.environ["CAHPP_RESOURCE_ROOT"] = str(resource_root())
    return path.resolve(), {**info, "smoke_test": args.smoke_test}
