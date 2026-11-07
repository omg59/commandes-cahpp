"""Dates françaises à l'écran ; les valeurs métier restent au format ISO."""

from datetime import date, datetime, time, timezone


def _datetime(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time())
    return datetime.fromisoformat(str(value).strip())


def format_date(value):
    if not value:
        return ""
    try:
        return _datetime(value).strftime("%d/%m/%Y")
    except ValueError:
        return str(value)


def format_datetime(value):
    if not value:
        return ""
    try:
        return _datetime(value).strftime("%d/%m/%Y à %H:%M")
    except ValueError:
        return str(value)


def format_month(value):
    if not value:
        return ""
    try:
        return datetime.strptime(str(value), "%Y-%m").strftime("%m/%Y")
    except ValueError:
        return str(value)


def parse_date(value):
    text = str(value).strip()
    try:
        if "/" in text:
            return datetime.strptime(text, "%d/%m/%Y").date()
        # Une ancienne date ISO collée depuis un export reste utilisable.
        return date.fromisoformat(text)
    except ValueError:
        raise ValueError(
            "Saisissez une date valide au format JJ/MM/AAAA (ex. 07/11/2026)."
        ) from None


def date_sort_key(value):
    if not value:
        return (0, datetime.min)
    try:
        parsed = _datetime(value)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return (1, parsed)
    except ValueError:
        return (2, str(value))
