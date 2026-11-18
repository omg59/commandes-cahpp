"""Partage du logo de l’établissement et copie locale pour les PDF."""

from __future__ import annotations

import hashlib
import io
import os
import uuid
from pathlib import Path

from PIL import Image

from .local_services import portable_path, resolve_portable_path

MAX_LOGO_BYTES = 4 * 1024 * 1024
PENDING_LOGO = "team_logo_pending"
IMAGE_EXTENSIONS = {"PNG": ".png", "JPEG": ".jpg"}


def _read(path: Path) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(MAX_LOGO_BYTES + 1)
    if len(data) > MAX_LOGO_BYTES:
        raise ValueError("Le logo ne doit pas dépasser 4 Mio.")
    return data


def _extension(data: bytes) -> str:
    try:
        with Image.open(io.BytesIO(data), formats=list(IMAGE_EXTENSIONS)) as image:
            if image.width * image.height <= 16_000_000:
                extension = IMAGE_EXTENSIONS[image.format]
                image.load()
                return extension
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise ValueError("Choisissez une image PNG ou JPEG valide pour le logo.") from exc
    raise ValueError("Le logo ne doit pas dépasser 16 millions de pixels.")


def _replace(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _cache(database, data: bytes) -> str:
    if not data:
        return ""
    digest = hashlib.sha256(data).hexdigest()
    directory = database.path.parent / f"{database.path.stem}-logos"
    for extension in IMAGE_EXTENSIONS.values():
        candidate = directory / (digest + extension)
        if candidate.is_file() and candidate.stat().st_size == len(data) and _read(candidate) == data:
            return portable_path(candidate)
    destination = directory / (digest + _extension(data))
    _replace(destination, data)
    return portable_path(destination)


def prepare_logo(database, value: str) -> str:
    if not value:
        return ""
    data = _read(resolve_portable_path(value))
    if not data:
        raise ValueError("Le fichier du logo est vide.")
    return _cache(database, data)


def sync_logo(database, directory: Path, workspace_id: str) -> bool:
    """À appeler sous le verrou des données d’équipe. Un fichier vide retire le logo."""
    settings = database.get_settings()
    value = settings.get("logo_path", "")
    pending = bool(workspace_id) and settings.get(PENDING_LOGO) == workspace_id
    shared = directory / "logo-etablissement.image"
    data = None
    try:
        if not pending:
            data = _read(shared)
    except FileNotFoundError:
        pass
    publish = pending or (data is None and bool(value))
    if publish:
        if value:
            data = _read(resolve_portable_path(value))
            if not data:
                raise ValueError("Le fichier du logo est vide.")
        else:
            data = b""
    if data is None:
        return False
    local = _cache(database, data)
    if publish:
        _replace(shared, data)
    if local != value or pending:
        database.save_settings({"logo_path": local, PENDING_LOGO: ""})
    return local != value or publish
