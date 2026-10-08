"""Formatting helpers and CSV export."""

import csv
from datetime import datetime

from appnames import display_name

DATE_FORMAT = "%d%m%y"


def format_duration(seconds, precise=False):
    """45s / 12m / 7h 15m / 3d 4h. precise=True also shows seconds."""
    seconds = int(max(0, seconds))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)

    if days:
        return f"{days}d {hours}h" if not precise else f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s" if precise else f"{minutes}m"
    return f"{secs}s"


def group_digits(number, lang="en"):
    """102672 -> 102.672 (tr) / 102,672 (en)"""
    grouped = f"{int(number):,}"
    return grouped.replace(",", ".") if lang == "tr" else grouped


def format_axis(seconds):
    """Axis label: short, single unit. 12h / 30m / 45s"""
    seconds = int(max(0, seconds))
    if seconds >= 86400:
        return f"{seconds / 86400:.0f}d"
    if seconds >= 3600:
        hours = seconds / 3600
        return f"{hours:.0f}h" if abs(hours - round(hours)) < 0.05 else f"{hours:.1f}h"
    if seconds >= 60:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def format_time(seconds):
    """Old format, kept for backward compatibility."""
    seconds = int(max(0, seconds))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    if days:
        return f"{days}:{hours:02}:{minutes:02}:{secs:02}"
    if hours:
        return f"{hours}:{minutes:02}:{secs:02}"
    return f"{minutes:02}:{secs:02}"


def format_percent(value, lang="en"):
    """58.8% (en) / %58,8 (tr)"""
    if lang == "tr":
        return "%" + f"{value:.1f}".replace(".", ",")
    return f"{value:.1f}%"


def format_delta(value, lang="en"):
    sign = "+" if value >= 0 else "−"
    return sign + format_percent(abs(value), lang).lstrip("+")


def parse_date(date_str):
    try:
        return datetime.strptime(date_str, DATE_FORMAT)
    except (ValueError, TypeError):
        return None


def format_date(date_str, months, short=True):
    """270126 -> 27 Jan"""
    parsed = parse_date(date_str)
    if not parsed:
        return date_str
    label = f"{parsed.day} {months[parsed.month - 1]}"
    return label if short else f"{label} {parsed.year}"


def export_csv(path, tracker, date_strs, hide_system=False):
    """Writes the period's per-day, per-app breakdown. Returns the row count."""
    from appnames import is_system

    rows = 0
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["date", "app", "display_name", "seconds", "duration"])
        for date_str in date_strs:
            parsed = parse_date(date_str)
            iso = parsed.strftime("%Y-%m-%d") if parsed else date_str
            day = tracker.day_totals(date_str)
            for app, seconds in sorted(day.items(), key=lambda x: -x[1]):
                if hide_system and is_system(app):
                    continue
                writer.writerow([iso, app, display_name(app), int(seconds),
                                 format_duration(seconds, precise=True)])
                rows += 1
    return rows
