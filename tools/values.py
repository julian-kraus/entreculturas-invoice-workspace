"""Parsing and comparing amounts, dates and text the same way everywhere."""

from __future__ import annotations

import re
import unicodedata
from datetime import date

MONTHS = {
    "jan": 1, "janv": 1, "janvier": 1, "january": 1, "enero": 1, "ene": 1,
    "feb": 2, "fev": 2, "fevr": 2, "fevrier": 2, "february": 2, "febrero": 2,
    "mar": 3, "mars": 3, "march": 3, "marzo": 3,
    "apr": 4, "avr": 4, "avril": 4, "april": 4, "abril": 4, "abr": 4,
    "may": 5, "mai": 5, "mayo": 5,
    "jun": 6, "juin": 6, "june": 6, "junio": 6,
    "jul": 7, "juil": 7, "juillet": 7, "july": 7, "julio": 7,
    "aug": 8, "aou": 8, "aout": 8, "august": 8, "agosto": 8, "ago": 8,
    "sep": 9, "sept": 9, "septembre": 9, "september": 9, "septiembre": 9,
    "oct": 10, "octobre": 10, "october": 10, "octubre": 10,
    "nov": 11, "novembre": 11, "november": 11, "noviembre": 11,
    "dec": 12, "decembre": 12, "december": 12, "diciembre": 12, "dic": 12,
}


def plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", text).strip().lower()


def parse_amount(value) -> float | None:
    """Read 30.000, 30 000, 1.234,56, 1,234.56 or 30000 FCFA as a number."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r"[^\d,.\-]", "", str(value).replace(" ", " ").replace(" ", ""))
    if not re.search(r"\d", text):
        return None
    if "," in text and "." in text:
        decimal = "," if text.rfind(",") > text.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        text = text.replace(thousands, "").replace(decimal, ".")
    elif "," in text or "." in text:
        sep = "," if "," in text else "."
        parts = text.split(sep)
        if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3):
            text = text.replace(sep, "")
        else:
            text = text.replace(sep, ".")
    try:
        return float(text)
    except ValueError:
        return None


def parse_date(value) -> date | None:
    """Read 28/08/2025, 2025-08-28, 28 août 2025 or 12 mars 2026."""
    if not value:
        return None
    text = plain(value)
    match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if match:
        year, month, day = (int(g) for g in match.groups())
        return _safe_date(year, month, day)
    match = re.search(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})", text)
    if match:
        day, month, year = (int(g) for g in match.groups())
        if year < 100:
            year += 2000
        return _safe_date(year, month, day)
    match = re.search(r"(\d{1,2})\s*(?:de\s+)?([a-z]+)\.?\s*(?:de\s+)?(\d{4})", text)
    if match and match.group(2) in MONTHS:
        return _safe_date(int(match.group(3)), MONTHS[match.group(2)], int(match.group(1)))
    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def same_value(expected, actual, kind: str = "text") -> bool:
    """Compare a confirmed answer with a result, tolerant of formatting."""
    if expected in (None, "") and actual in (None, ""):
        return True
    if expected in (None, "") or actual in (None, ""):
        return False
    if kind == "amount":
        a, b = parse_amount(expected), parse_amount(actual)
        return a is not None and b is not None and abs(a - b) < 0.01
    if kind == "date":
        a, b = parse_date(expected), parse_date(actual)
        if a and b:
            return a == b
    return plain(expected) == plain(actual)
