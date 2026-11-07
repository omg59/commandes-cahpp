from __future__ import annotations

import os
import sys
from pathlib import Path


def portable_root() -> Path:
    override = os.environ.get("CAHPP_PORTABLE_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


ROOT_DIR = portable_root()
RESOURCE_ROOT = (
    Path(getattr(sys, "_MEIPASS"))
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
    else Path(os.environ.get("CAHPP_RESOURCE_ROOT", ROOT_DIR)).expanduser().resolve()
)
RESOURCE_DIR = RESOURCE_ROOT / "ressources"
DATA_DIR = ROOT_DIR / "data"
EXPORT_DIR = ROOT_DIR / "exports"
BACKUP_DIR = ROOT_DIR / "sauvegardes"
DOCUMENTS_DIR = ROOT_DIR / "documents"
MAIL_PREP_DIR = ROOT_DIR / "envois"
DATABASE_PATH = DATA_DIR / "commandes_cahpp.sqlite3"


def ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    MAIL_PREP_DIR.mkdir(parents=True, exist_ok=True)
