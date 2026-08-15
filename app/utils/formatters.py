"""Formatting utilities for user-facing display."""

from datetime import datetime


def format_price(kopeks: int) -> str:
    """Format price in kopeks to rubles string. Examples: '299 ₽', '1 499 ₽'."""
    rubles = kopeks // 100
    if rubles == 0 and kopeks > 0:
        return f"0,{kopeks:02d} ₽"
    formatted = f"{rubles:,}".replace(",", " ")
    return f"{formatted} ₽"


def format_date(dt: datetime) -> str:
    """Format date as DD.MM.YYYY."""
    return dt.strftime("%d.%m.%Y")


def format_datetime(dt: datetime) -> str:
    """Format datetime as DD.MM.YYYY HH:MM."""
    return dt.strftime("%d.%m.%Y %H:%M")


def format_traffic(bytes_val: int) -> str:
    """Format bytes to human-readable traffic string.

    Returns '∞' for 0 (unlimited), otherwise GB or MB with one decimal.
    """
    if bytes_val <= 0:
        return "∞"

    gb = bytes_val / (1024 ** 3)
    if gb >= 1.0:
        if gb == int(gb):
            return f"{int(gb)} ГБ"
        return f"{gb:.1f} ГБ"

    mb = bytes_val / (1024 ** 2)
    if mb >= 1.0:
        if mb == int(mb):
            return f"{int(mb)} МБ"
        return f"{mb:.1f} МБ"

    kb = bytes_val / 1024
    return f"{kb:.1f} КБ"


def mask_key(url: str) -> str:
    """Mask a subscription key/URL, showing first 10 and last 4 characters."""
    if len(url) <= 14:
        return url
    return f"{url[:10]}***{url[-4:]}"
