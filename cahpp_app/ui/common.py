from __future__ import annotations

import calendar
import os
import re
import subprocess
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from tkinter import filedialog
from ..database import Database
from ..local_services import resolve_portable_path
from ..paths import EXPORT_DIR
from ..numbers import format_decimal, field_display_value


COLORS = {
    "nav": "#123A5A",
    "nav_hover": "#1A5276",
    "nav_active": "#0B2B43",
    "nav_indicator": "#65C7E8",
    "accent": "#1F6F9F",
    "accent_light": "#E8F2F8",
    "background": "#F3F6F8",
    "surface": "#FFFFFF",
    "text": "#1E2933",
    "muted": "#64748B",
    "border": "#D8E1E8",
    "success": "#277A53",
    "warning": "#A36400",
    "danger": "#A33A3A",
}


SYNC_INTERVAL_OPTIONS = {
    "15 secondes": "15",
    "30 secondes": "30",
    "1 minute": "60",
    "2 minutes": "120",
    "5 minutes": "300",
    "10 minutes": "600",
}


DOCUMENT_TYPES = (
    "Bon de livraison",
    "Confirmation de commande",
    "Facture",
    "Devis",
    "Avoir",
    "Correspondance",
    "Pièce jointe e-mail",
    "Autre…",
)


def format_number(value: object, decimals: int = 0) -> str:
    if value in (None, ""):
        return "—"
    number = Decimal(str(value))
    if decimals == 0 and number == number.to_integral():
        return f"{int(number):,}".replace(",", " ")
    text = format_decimal(number, decimals)
    return text


def format_price(value: object, decimals: int = 4) -> str:
    if value is None:
        return "Prix absent"
    return format_decimal(value, decimals) + " €"


def supplier_field_display_value(field: str, value: object) -> str:
    """Formate en français les montants, sans altérer les champs texte."""
    return field_display_value(field, value, {"minimum_order_ht", "franco_ht"})


def product_field_display_value(field: str, value: object) -> str:
    """Localise seulement les valeurs numériques éditables d'un article."""
    return field_display_value(field, value, {"conditionnement", "unit_price", "vat"})


def format_timestamp(value: object) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(str(value)).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return str(value)


def months_before(reference: date, months: int) -> date:
    months = max(0, int(months))
    absolute_month = reference.year * 12 + reference.month - 1 - months
    year, month_index = divmod(absolute_month, 12)
    month = month_index + 1
    day = min(reference.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def timestamp_is_due(value: str, days: int) -> bool:
    if not value.strip():
        return True
    try:
        when = datetime.fromisoformat(value)
    except ValueError:
        return True
    return datetime.now() - when >= timedelta(days=max(1, days))


def centered_window_position(
    parent_x: int,
    parent_y: int,
    parent_width: int,
    parent_height: int,
    window_width: int,
    window_height: int,
    screen_width: int,
    screen_height: int,
) -> tuple[int, int]:
    x = parent_x + (parent_width - window_width) // 2
    y = parent_y + (parent_height - window_height) // 2
    return (
        max(0, min(x, max(0, screen_width - window_width))),
        max(0, min(y, max(0, screen_height - window_height))),
    )


def format_pack(row) -> str:
    quantity = format_number(row["conditionnement"])
    detail = str(row["unit_packaging"] or "").strip()
    return f"{quantity} • {detail}" if detail else quantity


def open_path(path: Path | str) -> None:
    path = str(path)
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", path])


def safe_filename(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*]+', "-", value)
    value = re.sub(r"\s+", " ", value).strip(" .-")
    return value or "fournisseur"


def filter_supplier_names(names: list[str], query: str) -> list[str]:
    query = query.strip().casefold()
    if not query:
        return names
    return [name for name in names if query in name.casefold()]


def configured_pdf_directory(database: Database) -> Path:
    configured = database.get_settings().get("pdf_default_directory", "").strip()
    if configured:
        directory = resolve_portable_path(os.path.expandvars(configured))
        if directory.is_dir():
            return directory
    return EXPORT_DIR


def suggested_pdf_filename(database: Database, order) -> str:
    sequence = database.daily_supplier_order_sequence(int(order["id"]))
    suffix = "" if sequence == 1 else f"_{sequence}"
    supplier = safe_filename(str(order["supplier_name"]).title())
    return f"BC-{order['order_date']}{suffix}_{supplier}.pdf"


def fractional_carton_lines(lines: list[dict[str, object]]) -> list[str]:
    issues = []
    for line in lines:
        cartons = Decimal(str(line.get("cartons") or 0))
        if cartons != cartons.to_integral_value():
            issues.append(str(line.get("designation") or "Article"))
    return issues


def choose_pdf_path(parent, database: Database, order) -> Path | None:
    default_name = suggested_pdf_filename(database, order)
    selected = filedialog.asksaveasfilename(
        parent=parent,
        title="Enregistrer le bon de commande",
        initialdir=str(configured_pdf_directory(database)),
        initialfile=default_name,
        defaultextension=".pdf",
        filetypes=[("Document PDF", "*.pdf"), ("Tous les fichiers", "*.*")],
    )
    return Path(selected) if selected else None
