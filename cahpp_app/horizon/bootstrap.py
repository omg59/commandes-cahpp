"""Profils d'essai isolés ; ce module n'importe ni Qt ni les chemins métier."""

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


def profile_info(path: Path) -> dict:
    marker = path / MARKER
    if not marker.is_file():
        raise ValueError(
            "Ce dossier n'est pas un profil Horizon. Choisissez un dossier d'essai vide."
        )
    info = json.loads(marker.read_text(encoding="utf-8"))
    if info.get("application") != "commandes-cahpp-horizon" or info.get("format") != 1:
        raise ValueError("Profil Horizon non reconnu.")
    return info


def initialize_profile(path: Path, *, mode="demo") -> dict:
    path = path.expanduser().resolve()
    if (path / MARKER).exists():
        return profile_info(path)
    if path.exists() and any(path.iterdir()):
        raise ValueError(
            "Horizon utilise un dossier d'essai vide et ne peut pas ouvrir directement votre installation habituelle."
        )
    path.mkdir(parents=True, exist_ok=True)
    info = {
        "application": "commandes-cahpp-horizon",
        "format": 1,
        "mode": mode,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    (path / MARKER).write_text(json.dumps(info, indent=2), encoding="utf-8")
    return info


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
                or not 1 <= version <= 15
            ):
                raise ValueError(
                    "Choisissez une base Commandes CAHPP de schéma 15 ou antérieur."
                )
            with closing(sqlite3.connect(target)) as local, local:
                origin.backup(local)
                if local.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError("Le contrôle d'intégrité de la copie a échoué.")
                local.execute(
                    "UPDATE settings SET value='0' WHERE key='collaboration_enabled'"
                )
                local.execute(
                    "UPDATE settings SET value='' WHERE key IN ('collaboration_root','shared_folder','shared_workspace_path','collaboration_workspace_id','collaboration_last_sync_at','collaboration_catalog_hash','collaboration_catalog_version','pdf_default_directory')"
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
                        / (uuid.uuid4().hex + original.suffix)
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


def configure(argv=None) -> tuple[Path, dict]:
    parser = argparse.ArgumentParser(
        description="Horizon : interface Qt sur données d'essai isolées"
    )
    parser.add_argument(
        "--profile", type=Path, help="Profil Horizon existant ou dossier vide"
    )
    parser.add_argument(
        "--copy-database", type=Path, help="Créer une copie isolée d'une base CAHPP"
    )
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.profile and args.copy_database:
        parser.error("Choisir un profil ou une base à copier.")
    path = (
        copy_database(args.copy_database, data_root() / "profils")
        if args.copy_database
        else (args.profile or data_root() / "demonstration")
    )
    info = initialize_profile(path)
    os.environ["CAHPP_PORTABLE_ROOT"] = str(path.resolve())
    os.environ["CAHPP_RESOURCE_ROOT"] = str(resource_root())
    return path.resolve(), {**info, "smoke_test": args.smoke_test}
