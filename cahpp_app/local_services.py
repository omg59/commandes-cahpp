from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .database import Database
from .paths import DATABASE_PATH, DOCUMENTS_DIR, MAIL_PREP_DIR, ROOT_DIR

SHARED_WORKSPACE_DIR: Path | None = None

MAIL_TEMPLATE_VARIABLES = {
    "order_number": "numéro du bon de commande",
    "date": "date du bon au format JJ/MM/AAAA",
    "order_date": "date du bon au format AAAA-MM-JJ",
    "supplier": "nom du fournisseur",
    "supplier_email": "adresse e-mail du fournisseur",
    "customer_number": "numéro client chez le fournisseur",
    "total_ht": "montant total HT",
    "total_ttc": "montant total TTC",
    "establishment_name": "nom de l'établissement",
    "establishment_subtitle": "service ou sous-titre de l'établissement",
}


def safe_filename(value: str) -> str:
    forbidden = '<>:"/\\|?*'
    cleaned = "".join("-" if char in forbidden else char for char in value)
    cleaned = " ".join(cleaned.split()).strip(" .-")
    return cleaned or "document"


def resolve_portable_path(value: str | Path) -> Path:
    if isinstance(value, str) and value.startswith("shared:"):
        if SHARED_WORKSPACE_DIR is None:
            return Path(value.removeprefix("shared:"))
        relative = Path(value.removeprefix("shared:"))
        candidate = (SHARED_WORKSPACE_DIR / relative).resolve()
        candidate.relative_to(SHARED_WORKSPACE_DIR.resolve())
        return candidate
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path.resolve()


def portable_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    if SHARED_WORKSPACE_DIR is not None:
        try:
            relative = resolved.relative_to(SHARED_WORKSPACE_DIR.resolve())
            return "shared:" + relative.as_posix()
        except ValueError:
            pass
    try:
        return resolved.relative_to(ROOT_DIR.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def configure_shared_workspace(path: str | Path | None) -> None:
    global SHARED_WORKSPACE_DIR
    SHARED_WORKSPACE_DIR = (
        Path(path).expanduser().resolve()
        if str(path or "").strip()
        else None
    )


def _available_destination(directory: Path, filename: str) -> Path:
    candidate = directory / safe_filename(filename)
    stem = candidate.stem
    suffix = candidate.suffix
    index = 2
    while candidate.exists():
        candidate = directory / f"{stem}_{index}{suffix}"
        index += 1
    return candidate


def attach_document(
    database: Database,
    order_id: int,
    source: str | Path,
    kind: str,
    include_in_email: bool = False,
) -> int:
    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError(source)
    order, _ = database.get_order(order_id)
    # La copie locale reste la source de travail. En mode collaboratif, la
    # publication de la commande crée ensuite une seconde copie sur le partage.
    # Le document demeure ainsi consultable lorsque le réseau est indisponible.
    directory = DOCUMENTS_DIR / safe_filename(order["order_number"])
    directory.mkdir(parents=True, exist_ok=True)
    destination = _available_destination(directory, source.name)
    shutil.copy2(source, destination)
    return database.add_order_attachment(
        order_id=order_id,
        kind=kind,
        display_name=destination.name,
        stored_path=portable_path(destination),
        include_in_email=include_in_email,
    )


def remove_document(database: Database, attachment_id: int) -> None:
    attachment = database.get_order_attachment(attachment_id)
    if attachment is None:
        return
    path = resolve_portable_path(attachment["stored_path"])
    if path.is_file():
        path.unlink()
    database.delete_order_attachment(attachment_id)


def create_complete_backup(
    database: Database, destination: str | Path
) -> Path:
    destination = Path(destination)
    if destination.suffix.lower() != ".zip":
        destination = destination.with_suffix(".zip")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="commandes-cahpp-") as temp_name:
        temp = Path(temp_name)
        database_copy = temp / "data" / DATABASE_PATH.name
        database.backup(database_copy)
        manifest = {
            "application": "Commandes CAHPP",
            "backup_format": 1,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "database": f"data/{DATABASE_PATH.name}",
            "documents": "documents/",
        }
        (temp / "sauvegarde.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        with zipfile.ZipFile(
            destination, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for path in sorted(temp.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(temp))
            if DOCUMENTS_DIR.is_dir():
                for path in sorted(DOCUMENTS_DIR.rglob("*")):
                    if path.is_file():
                        archive.write(
                            path,
                            Path("documents") / path.relative_to(DOCUMENTS_DIR),
                        )
    return destination


class _SafeTemplate(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _render_template(template: str, values: dict[str, object]) -> str:
    return template.format_map(_SafeTemplate(values))


def _mail_compose_url(
    base_url: str, recipient: str, subject: str, body: str
) -> str:
    parsed = urlparse(base_url)
    parameters = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if parsed.scheme.lower() == "mailto":
        parameters.update({"subject": subject, "body": body})
        return urlunparse(
            parsed._replace(path=recipient, query=urlencode(parameters))
        )
    if "mail.google." in parsed.netloc.lower():
        parameters.update(
            {
                "view": "cm",
                "fs": "1",
                "to": recipient,
                "su": subject,
                "body": body,
            }
        )
    else:
        parameters.update(
            {"to": recipient, "subject": subject, "body": body}
        )
    return urlunparse(parsed._replace(query=urlencode(parameters)))


def prepare_mail_order(
    database: Database, order_id: int
) -> tuple[str, Path, list[Path]]:
    order, _ = database.get_order(order_id)
    if not order["supplier_email"]:
        raise ValueError(
            "Aucune adresse e-mail n'est configurée pour ce fournisseur."
        )
    pdf_path = resolve_portable_path(order["pdf_path"]) if order["pdf_path"] else None
    if pdf_path is None or not pdf_path.is_file():
        raise ValueError("Générez d'abord le PDF de cette commande.")

    staging = MAIL_PREP_DIR / safe_filename(order["order_number"])
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    sources = [pdf_path]
    for attachment in database.list_order_attachments(order_id):
        if attachment["include_in_email"]:
            path = resolve_portable_path(attachment["stored_path"])
            if path.is_file():
                sources.append(path)

    prepared: list[Path] = []
    for source in sources:
        destination = _available_destination(staging, source.name)
        shutil.copy2(source, destination)
        prepared.append(destination)

    settings = database.get_settings()
    order_date = datetime.fromisoformat(order["order_date"]).strftime("%d/%m/%Y")
    values: dict[str, object] = {
        "order_number": order["order_number"],
        "date": order_date,
        "order_date": order["order_date"],
        "supplier": order["supplier_name"],
        "supplier_email": order["supplier_email"],
        "total_ht": f"{float(order['total_ht']):.2f}".replace(".", ","),
        "total_ttc": f"{float(order['total_ttc']):.2f}".replace(".", ","),
        "establishment_name": settings.get("establishment_name", ""),
        "establishment_subtitle": settings.get(
            "establishment_subtitle", ""
        ),
        "customer_number": order["customer_number"] or "",
    }
    subject = _render_template(
        settings.get("email_subject_template", ""), values
    )
    body = _render_template(settings.get("email_body_template", ""), values)
    compose_url = _mail_compose_url(
        settings.get("mail_compose_url", DEFAULT_MAIL_URL),
        order["supplier_email"],
        subject,
        body,
    )
    return compose_url, staging, prepared


def mark_order_sent(database: Database, order_id: int) -> bool:
    """Marquer la commande envoyée et supprimer ses copies de préparation."""
    database.update_order_status(order_id, "Envoyée")
    order, _ = database.get_order(order_id)
    staging = MAIL_PREP_DIR / safe_filename(order["order_number"])
    if not staging.exists():
        return False
    if staging.is_symlink() or not staging.is_dir():
        raise OSError(
            f"Le chemin de préparation n'est pas un dossier valide : {staging}"
        )
    shutil.rmtree(staging)
    return True


DEFAULT_MAIL_URL = "https://mail.google.com/mail/?view=cm&fs=1"

# Alias conservé pour les scripts créés avec les prototypes précédents.
prepare_gmail_order = prepare_mail_order
