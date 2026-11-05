"""Conversion et affichage des nombres, sans normaliser les champs texte."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def parse_decimal(
    value: object,
    label: str = "Valeur",
    *,
    minimum: Decimal | int | None = None,
    maximum: Decimal | int | None = None,
) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{label} doit être un nombre.")
    text = (
        str(value).strip().replace("\u00a0", "").replace("\u202f", "").replace(" ", "")
    )
    try:
        number = Decimal(text.replace(",", "."))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label} doit être un nombre valide.") from None
    if not number.is_finite():
        raise ValueError(f"{label} doit être un nombre fini.")
    if minimum is not None and number < minimum:
        raise ValueError(f"{label} doit être supérieur ou égal à {minimum}.")
    if maximum is not None and number > maximum:
        raise ValueError(f"{label} doit être inférieur ou égal à {maximum}.")
    return number


def format_decimal(value: object, decimals: int) -> str:
    number = parse_decimal(value)
    quantum = Decimal(1).scaleb(-decimals)
    try:
        return format(
            number.quantize(quantum, rounding=ROUND_HALF_UP), f".{decimals}f"
        ).replace(".", ",")
    except InvalidOperation:
        raise ValueError("Le nombre est trop grand pour être affiché.") from None


def field_display_value(field: str, value: object, numeric_fields: set[str]) -> str:
    if value is None:
        return ""
    text = str(value)
    return text.replace(".", ",") if field in numeric_fields else text
