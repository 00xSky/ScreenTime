"""Generates sentences from the data.

A raw number says little on its own. This module derives readable
observations such as "4 hours less than last week", "your busiest day
is Saturday", "half the time in one app". Only notable ones are returned.
"""

from appnames import display_name, is_system
from i18n import t, weekdays, months
from utils import format_duration, format_percent, format_date

# Minimum difference for an observation to make the list
MIN_CHANGE_PCT = 3.0
MIN_CHANGE_SECONDS = 600
MIN_PEAK_PCT = 15.0
MIN_CONCENTRATION_PCT = 40.0


def _visible(stats, hide_system):
    if not hide_system:
        return stats
    return {k: v for k, v in stats.items() if not is_system(k)}


def build(tracker, period, lang, hide_system, dates, stats):
    """Returns a list of (emphasis, text) pairs."""
    found = []
    total = sum(stats.values())
    if not total:
        return found

    previous_dates = tracker.previous_period_dates(period)
    previous = _visible(tracker.aggregate(previous_dates), hide_system) \
        if previous_dates else {}
    previous_total = sum(previous.values())

    found += _change(total, previous_total, period, lang)
    found += _mover(stats, previous, previous_total, lang)
    found += _peak_weekday(tracker, dates, lang)
    found += _concentration(stats, total, lang)
    found += _newcomer(stats, previous, previous_total, lang)
    # Without a previous period (all time) no comparison sentences can be made;
    # then derive observations from the history itself
    if len(found) < 3:
        found += _extremes(tracker, dates, lang)
        found += _coverage(tracker, dates, lang)
    return found[:3]


def _change(total, previous_total, period, lang):
    if not previous_total:
        return []
    delta = total - previous_total
    pct = delta / previous_total * 100
    if abs(pct) < MIN_CHANGE_PCT or abs(delta) < MIN_CHANGE_SECONDS:
        return [("flat", t(lang, "insight_steady"))]
    key = "insight_down" if delta < 0 else "insight_up"
    return [("good" if delta < 0 else "warn",
             t(lang, key, time=format_duration(abs(delta)),
               pct=format_percent(abs(pct), lang)))]


def _mover(stats, previous, previous_total, lang):
    if not previous_total:
        return []
    best_app, best_delta = None, 0
    for app in set(stats) | set(previous):
        delta = stats.get(app, 0) - previous.get(app, 0)
        if abs(delta) > abs(best_delta):
            best_app, best_delta = app, delta
    if not best_app or abs(best_delta) < MIN_CHANGE_SECONDS:
        return []
    key = "insight_mover_down" if best_delta < 0 else "insight_mover_up"
    return [("good" if best_delta < 0 else "warn",
             t(lang, key, app=display_name(best_app),
               time=format_duration(abs(best_delta))))]


def _peak_weekday(tracker, dates, lang):
    buckets = [[] for _ in range(7)]
    for date_str in dates:
        parsed = tracker.parse(date_str)
        if parsed is None or not tracker.has_record(date_str):
            continue
        buckets[parsed.weekday()].append(sum(tracker.day_totals(date_str).values()))

    averages = [(sum(values) / len(values)) if values else 0 for values in buckets]
    overall = [v for v in averages if v]
    if len(overall) < 3:
        return []

    mean = sum(overall) / len(overall)
    peak_index = averages.index(max(averages))
    if not mean or not averages[peak_index]:
        return []
    above = (averages[peak_index] - mean) / mean * 100
    if above < MIN_PEAK_PCT:
        return []
    return [("info", t(lang, "insight_peak_day",
                       day=weekdays(lang)[peak_index],
                       pct=format_percent(above, lang)))]


def _concentration(stats, total, lang):
    if not stats:
        return []
    app, seconds = max(stats.items(), key=lambda x: x[1])
    share = seconds / total * 100
    if share < MIN_CONCENTRATION_PCT:
        return []
    return [("info", t(lang, "insight_concentration",
                       app=display_name(app),
                       pct=format_percent(share, lang)))]


def _newcomer(stats, previous, previous_total, lang):
    if not previous_total:
        return []
    fresh = [(app, seconds) for app, seconds in stats.items()
             if app not in previous and seconds >= MIN_CHANGE_SECONDS]
    if not fresh:
        return []
    app, seconds = max(fresh, key=lambda x: x[1])
    return [("info", t(lang, "insight_new",
                       app=display_name(app), time=format_duration(seconds)))]


def _extremes(tracker, dates, lang):
    """Busiest and quietest recorded day."""
    totals = []
    for date_str in dates:
        if not tracker.has_record(date_str):
            continue
        value = sum(_visible(tracker.day_totals(date_str), True).values())
        if value:
            totals.append((date_str, value))
    if len(totals) < 5:
        return []

    month_names = months(lang)
    busiest = max(totals, key=lambda x: x[1])
    quiet = min(totals, key=lambda x: x[1])
    found = [("info", t(lang, "insight_busiest",
                        date=format_date(busiest[0], month_names),
                        time=format_duration(busiest[1])))]
    if quiet[1] * 3 < busiest[1]:
        found.append(("good", t(lang, "insight_quiet",
                                date=format_date(quiet[0], month_names),
                                time=format_duration(quiet[1]))))
    return found


def _coverage(tracker, dates, lang):
    """Days without a record: averages can be misleading because of them."""
    missing = sum(1 for date_str in dates if not tracker.has_record(date_str))
    if missing < 3:
        return []
    return [("flat", t(lang, "insight_coverage", n=missing, total=len(dates)))]
