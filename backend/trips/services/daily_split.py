"""
Splits a continuous list of HOS Segments (which may span multiple days)
into per-day chunks suitable for rendering as individual FMCSA log sheets.

Any segment crossing midnight is cut into two pieces, one per day.
"""

from datetime import datetime, timedelta, timezone
from .hos_engine import Segment, elapsed_hours


def _instant(dt: datetime) -> datetime:
    """
    A form of `dt` whose ordering reflects real time.

    Comparing two datetimes that share a tzinfo object compares their wall
    clock fields and ignores the offset entirely — and ZoneInfo caches one
    instance per zone, so every datetime here shares one. On the day the clocks
    go back, an hour-long segment running 01:16 CDT to 01:16 CST then compares
    as equal: `while seg_start < seg_end` is false, the loop never runs, and the
    segment drops off the log taking its duty hours with it. In UTC the ordering
    is unambiguous.
    """
    return dt.astimezone(timezone.utc) if dt.tzinfo is not None else dt

def _midnight_on(dt: datetime) -> datetime:
    """
    Local midnight opening the calendar day `dt` falls in.

    Uses replace() rather than rebuilding the datetime so that whatever zone the
    segments carry survives: constructing a fresh naive midnight and comparing it
    against a zone-aware segment raises TypeError, and a log day boundary is a
    *local* midnight at the home terminal, not a UTC one.
    """
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _midnight_after(dt: datetime) -> datetime:
    """
    Local midnight closing the calendar day `dt` falls in.

    Day boundaries are deliberately wall-clock arithmetic, unlike the durations
    in hos_engine: a calendar day ends at the next midnight on the driver's
    clock whether or not the clocks changed inside it. On a DST changeover that
    day genuinely holds 23 or 25 hours, and the log sheet should say so.
    """
    return _midnight_on(dt) + timedelta(days=1)


def _clock(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def _end_clock(start: datetime, end: datetime) -> str:
    """Midnight closing a day reads as 24:00, not 00:00 of the next one."""
    return "24:00" if end.hour == 0 and end.minute == 0 and end > start else _clock(end)


def _is_invisible(start: datetime, end: datetime) -> bool:
    """
    True when a piece is too short for the grid to express.

    The log is drawn and totalled to the minute, so a piece whose start and end
    fall in the same minute has nowhere to be drawn: it renders as a zero-width
    mark yet still contributes a remark naming a town the driver drove straight
    through. These come from a constraint landing a fraction of a mile from the
    end of a leg — a fuel stop falling just short of the drop-off, say. Dropping
    them costs under a minute of the day's total, well inside the two decimal
    places the totals are reported to.

    Duration is checked before the clock reading, because on the day the clocks
    go back an hour repeats: an hour-long pickup can begin at 01:16 CDT and end
    at 01:16 CST. Judging by the reading alone called that zero-length and threw
    the hour away, understating both the day's total and the 70-hour cycle.
    """
    if elapsed_hours(start, end) >= 1 / 60:
        return False
    return _clock(start) == _end_clock(start, end)


def split_into_days(segments: list[Segment], locate=None) -> list[dict]:
    """
    Returns a list of day dicts:
        {
            "day_number": int,
            "date": date,
            "segments": [{"status", "start" (HH:MM), "end" (HH:MM), "hours",
                          "label", "remark"}],
            "totals": {"OFF_DUTY": float, "SLEEPER_BERTH": float,
                       "DRIVING": float, "ON_DUTY": float}
        }

    `locate` is an optional callable taking (leg_index, miles_into_leg) and
    returning a "City, ST" string — typically RouteLocator.locate. When
    supplied, every genuine change of duty status gets a "remark" naming where
    it happened, as the FMCSA log form requires. Segments we synthesise
    ourselves (off-duty padding, and the tail of a segment that ran past
    midnight) are not status changes, so they carry an empty remark.
    """
    if not segments:
        return []

    def remark_for(seg: Segment) -> str:
        if locate is None:
            return ""
        return locate(seg.leg_index, seg.miles_into_leg)

    days = []
    day_number = 1
    # Each day is anchored to the local midnight that opens it rather than to a
    # bare date, so every boundary we derive inherits the segments' timezone.
    # Rebuilding one from a date would produce a naive datetime that cannot be
    # compared against a zone-aware segment.
    current_day_start = _midnight_on(segments[0].start)
    current_segments = []
    totals = {"OFF_DUTY": 0.0, "SLEEPER_BERTH": 0.0, "DRIVING": 0.0, "ON_DUTY": 0.0}
    # Where the last entry actually finished, kept as a datetime rather than
    # recovered from its "HH:MM" rendering. That rendering is lossy: on the day
    # the clocks go back, "01:32" names two different moments an hour apart, and
    # rebuilding one picked the earlier by default — padding the rest of the day
    # from an hour too early and inventing a 26th hour.
    last_end = current_day_start

    def flush():
        nonlocal current_segments, totals, day_number
        if current_segments:
            days.append({
                "day_number": day_number,
                "date": current_day_start.date(),
                "segments": current_segments,
                "totals": totals,
            })
        day_number += 1

    def _append(status, start, end, label="", remark=""):
        nonlocal current_segments, totals, last_end
        hours = elapsed_hours(start, end)
        if hours <= 0 or _is_invisible(start, end):
            return
        current_segments.append({
            "status": status,
            "label": label,
            "start": _clock(start),
            "end": _end_clock(start, end),
            "hours": round(hours, 2),
            "remark": remark,
        })
        totals[status] += hours
        last_end = end

    # Pad the very start of day 1 with OFF_DUTY from midnight to the first
    # activity, so every log sheet totals a full 24 hours (real ELD logs
    # always account for the whole calendar day).
    if segments[0].start > current_day_start:
        _append("OFF_DUTY", current_day_start, segments[0].start, label="Off duty")

    for seg in segments:
        seg_start = seg.start
        seg_end = seg.end
        # Only the first piece of a segment marks the actual status change; if
        # it spills past midnight the remainder is a continuation, not a change.
        pending_remark = remark_for(seg)

        while _instant(seg_start) < _instant(seg_end):
            boundary = _midnight_after(seg_start)
            piece_end = boundary if _instant(boundary) < _instant(seg_end) else seg_end

            if seg_start.date() != current_day_start.date():
                # Pad the end of the day we're leaving up to midnight, then
                # start a fresh day padded from midnight to this activity.
                day_end = current_day_start + timedelta(days=1)
                if current_segments and _instant(last_end) < _instant(day_end):
                    _append("OFF_DUTY", last_end, day_end, label="Off duty")
                flush()
                current_day_start = _midnight_on(seg_start)
                current_segments = []
                totals = {"OFF_DUTY": 0.0, "SLEEPER_BERTH": 0.0, "DRIVING": 0.0, "ON_DUTY": 0.0}
                last_end = current_day_start
                if _instant(current_day_start) < _instant(seg_start):
                    _append("OFF_DUTY", current_day_start, seg_start, label="Off duty")

            hours = elapsed_hours(seg_start, piece_end)
            if hours > 0 and not _is_invisible(seg_start, piece_end):
                current_segments.append({
                    "status": seg.status,
                    "label": seg.label,
                    "start": _clock(seg_start),
                    "end": _end_clock(seg_start, piece_end),
                    "hours": round(hours, 2),
                    "remark": pending_remark,
                })
                totals[seg.status] += hours
                pending_remark = ""
                last_end = piece_end

            seg_start = piece_end

    # Pad the end of the final day up to midnight (driver considered off
    # duty for the remainder of the calendar day after the trip finishes).
    final_day_end = current_day_start + timedelta(days=1)
    if current_segments and _instant(last_end) < _instant(final_day_end):
        _append("OFF_DUTY", last_end, final_day_end, label="Off duty")

    flush()
    return days
