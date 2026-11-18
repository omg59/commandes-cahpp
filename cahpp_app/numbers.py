"""Conversion et affichage des nombres, sans normaliser les champs texte."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext


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
    try:
        return format(round_decimal(number, decimals), f".{decimals}f").replace(".", ",")
    except InvalidOperation:
        raise ValueError("Le nombre est trop grand pour être affiché.") from None


def round_decimal(number: Decimal, decimals: int) -> Decimal:
    with localcontext() as context:
        context.prec = max(context.prec, len(number.as_tuple().digits), number.adjusted() + decimals + 2)
        return number.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)


def decimal_product(*values: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = max(context.prec, sum(len(value.as_tuple().digits) for value in values))
        product = Decimal(1)
        for value in values:
            product *= value
        return product


def add_decimal(left: Decimal, right: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = max(left.adjusted(), right.adjusted()) - min(
            left.as_tuple().exponent, right.as_tuple().exponent
        ) + 2
        return left + right


def sum_decimals(values) -> Decimal:
    total = Decimal(0)
    for value in values:
        total = add_decimal(total, value)
    return total


def line_amount(units: Decimal, price: Decimal) -> Decimal:
    return round_decimal(decimal_product(units, price), 4)


def line_tax(net: Decimal, rate: Decimal) -> Decimal:
    return round_decimal(decimal_product(net, rate, Decimal("0.01")), 4)


def field_display_value(field: str, value: object, numeric_fields: set[str]) -> str:
    if value is None:
        return ""
    text = str(value)
    return text.replace(".", ",") if field in numeric_fields else text
