"""
Splits a continuous list of HOS Segments (which may span multiple days)
into per-day chunks suitable for rendering as individual FMCSA log sheets.

Any segment crossing midnight is cut into two pieces, one per day.
"""

from datetime import datetime, timedelta
from .hos_engine import Segment


def _midnight_after(dt: datetime) -> datetime:
    return datetime(dt.year, dt.month, dt.day) + timedelta(days=1)


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
    current_date = segments[0].start.date()
    current_segments = []
    totals = {"OFF_DUTY": 0.0, "SLEEPER_BERTH": 0.0, "DRIVING": 0.0, "ON_DUTY": 0.0}

    def flush():
        nonlocal current_segments, totals, day_number
        if current_segments:
            days.append({
                "day_number": day_number,
                "date": current_date,
                "segments": current_segments,
                "totals": totals,
            })
        day_number += 1

    def _append(status, start, end, label="", remark=""):
        nonlocal current_segments, totals
        hours = (end - start).total_seconds() / 3600
        if hours <= 0:
            return
        current_segments.append({
            "status": status,
            "label": label,
            "start": start.strftime("%H:%M"),
            "end": "24:00" if end.hour == 0 and end.minute == 0 and end > start else end.strftime("%H:%M"),
            "hours": round(hours, 2),
            "remark": remark,
        })
        totals[status] += hours

    # Pad the very start of day 1 with OFF_DUTY from midnight to the first
    # activity, so every log sheet totals a full 24 hours (real ELD logs
    # always account for the whole calendar day).
    day_start = datetime(current_date.year, current_date.month, current_date.day)
    if segments[0].start > day_start:
        _append("OFF_DUTY", day_start, segments[0].start, label="Off duty")

    for seg in segments:
        seg_start = seg.start
        seg_end = seg.end
        # Only the first piece of a segment marks the actual status change; if
        # it spills past midnight the remainder is a continuation, not a change.
        pending_remark = remark_for(seg)

        while seg_start < seg_end:
            boundary = _midnight_after(seg_start)
            piece_end = min(seg_end, boundary)

            if seg_start.date() != current_date:
                # Pad the end of the day we're leaving up to midnight, then
                # start a fresh day padded from midnight to this activity.
                day_end = datetime(current_date.year, current_date.month, current_date.day) + timedelta(days=1)
                if current_segments and current_segments[-1]["end"] != "24:00":
                    last_end = datetime.combine(current_date, datetime.strptime(current_segments[-1]["end"], "%H:%M").time())
                    _append("OFF_DUTY", last_end, day_end, label="Off duty")
                flush()
                current_date = seg_start.date()
                current_segments = []
                totals = {"OFF_DUTY": 0.0, "SLEEPER_BERTH": 0.0, "DRIVING": 0.0, "ON_DUTY": 0.0}
                new_day_start = datetime(current_date.year, current_date.month, current_date.day)
                if seg_start > new_day_start:
                    _append("OFF_DUTY", new_day_start, seg_start, label="Off duty")

            hours = (piece_end - seg_start).total_seconds() / 3600
            current_segments.append({
                "status": seg.status,
                "label": seg.label,
                "start": seg_start.strftime("%H:%M"),
                "end": piece_end.strftime("%H:%M") if piece_end.hour != 0 or piece_end.minute != 0 or piece_end == seg_start else "24:00",
                "hours": round(hours, 2),
                "remark": pending_remark,
            })
            totals[seg.status] += hours
            pending_remark = ""

            seg_start = piece_end

    # Pad the end of the final day up to midnight (driver considered off
    # duty for the remainder of the calendar day after the trip finishes).
    if current_segments and current_segments[-1]["end"] != "24:00":
        last_end = datetime.combine(current_date, datetime.strptime(current_segments[-1]["end"], "%H:%M").time())
        day_end = datetime(current_date.year, current_date.month, current_date.day) + timedelta(days=1)
        _append("OFF_DUTY", last_end, day_end, label="Off duty")

    flush()
    return days
