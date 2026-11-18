"""Validation des pièces jointes reçues et de celles déjà présentes sur les PC."""

import io
import re
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from ..local_services import safe_filename

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
EXTENSIONS = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}
MIME_BY_EXTENSION = {suffix: mime for mime, suffix in EXTENSIONS.items()} | {".jpeg": "image/jpeg"}
MOBILE_NAME = re.compile(r"-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")


def validate_document(data, mime):
    if not data or len(data) > MAX_DOCUMENT_BYTES:
        raise ValueError("Le document mobile doit faire entre 1 octet et 10 Mio.")
    if mime == "application/pdf":
        if re.match(rb"%PDF-[12]\.[0-9][\r\n]", data) and data.rstrip(b" \t\r\n\f\0").endswith(b"%%EOF"):
            return
    elif mime in ("image/jpeg", "image/png"):
        expected = "JPEG" if mime == "image/jpeg" else "PNG"
        try:
            with Image.open(io.BytesIO(data), formats=[expected]) as image:
                if image.width * image.height <= 40_000_000:
                    if expected == "JPEG":
                        image.load()
                    else:
                        image.verify()
                    return
        except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError):
            pass
    raise ValueError("Le contenu du document mobile ne correspond pas à un PDF, JPEG ou PNG valide.")


def document_filename(name, key, mime):
    if not isinstance(name, str) or not isinstance(mime, str) or mime not in EXTENSIONS:
        raise ValueError("Seuls les documents PDF, JPEG et PNG sont acceptés depuis le téléphone.")
    stem = "".join(char for char in Path(name).stem if char.isprintable())
    return f"{safe_filename(stem)[:100]}-{key}{EXTENSIONS[mime]}"


def check_mobile_attachment(path, display_name=""):
    # La copie sur le partage et le cache PC conservent le nom portant l’UUID
    # de l’action, même quand ils ne conservent pas l’arborescence d’origine.
    if not any(MOBILE_NAME.search(Path(name).stem) for name in (path.name, display_name)):
        return
    mime = MIME_BY_EXTENSION.get(path.suffix.lower())
    if mime is None:
        raise ValueError("Extension de pièce jointe mobile non autorisée. Rattachez le document d’origine au format PDF, JPEG ou PNG.")
    with path.open("rb") as stream:
        validate_document(stream.read(MAX_DOCUMENT_BYTES + 1), mime)
