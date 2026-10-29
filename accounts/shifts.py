from datetime import time, datetime, timedelta
from zoneinfo import ZoneInfo
from django.conf import settings
from django.utils import timezone
from accounts.models import User

CAIRO_TZ = ZoneInfo("Africa/Cairo")

SHIFT_START_TIMES = {
    User.Shift.FIRST: time(7, 0),
    User.Shift.SECOND: time(15, 0),
    User.Shift.THIRD: time(23, 0),
}

SHIFT_WINDOWS = {
    User.Shift.FIRST: {
        "code": User.Shift.FIRST,
        "name": "الوردية الأولى (صباحية)",
        "short_name": "الصباحية",
        "start": time(7, 0),
        "end": time(15, 0),
        "duration_hours": 8,
        "hours_display": "من 7:00 صباحاً إلى 3:00 مساءً",
        "short_hours": "7:00 ص - 3:00 م",
        "allows_maintenance": True,
        "allows_production": True,
    },
    User.Shift.SECOND: {
        "code": User.Shift.SECOND,
        "name": "الوردية الثانية (مسائية)",
        "short_name": "المسائية",
        "start": time(15, 0),
        "end": time(23, 0),
        "duration_hours": 8,
        "hours_display": "من 3:00 مساءً إلى 11:00 مساءً",
        "short_hours": "3:00 م - 11:00 م",
        "allows_maintenance": False,
        "allows_production": True,
    },
    User.Shift.THIRD: {
        "code": User.Shift.THIRD,
        "name": "الوردية الثالثة (ليلية)",
        "short_name": "الليلية",
        "start": time(23, 0),
        "end": time(7, 0),
        "duration_hours": 8,
        "hours_display": "من 11:00 مساءً إلى 7:00 صباحاً",
        "short_hours": "11:00 م - 7:00 ص",
        "allows_maintenance": False,
        "allows_production": True,
    },
}


def get_cairo_time(now=None):
    """
    Returns the given or current datetime in Africa/Cairo timezone.
    """
    if now is None:
        return timezone.localtime()
    if isinstance(now, datetime):
        if timezone.is_naive(now):
            return now.replace(tzinfo=CAIRO_TZ)
        return now.astimezone(CAIRO_TZ)
    return now


def get_current_shift_by_time(now=None):
    """
    Returns the active shift code (FIRST, SECOND, THIRD) for the given datetime in Africa/Cairo.
    - FIRST (Morning):  07:00:00 <= t < 15:00:00  (8 hours)
    - SECOND (Evening): 15:00:00 <= t < 23:00:00  (8 hours)
    - THIRD (Night):    23:00:00 <= t or t < 07:00:00 (8 hours)
    """
    dt = get_cairo_time(now)
    t = dt.time() if hasattr(dt, "time") else dt

    if time(7, 0) <= t < time(15, 0):
        return User.Shift.FIRST
    elif time(15, 0) <= t < time(23, 0):
        return User.Shift.SECOND
    else:
        return User.Shift.THIRD


def get_shift_range(shift_code, report_date, grace_hours=2):
    """
    Calculates (shift_start_dt, shift_end_dt, window_end_dt) for a shift on report_date.
    All datetimes are timezone-aware in Africa/Cairo.
    """
    start_time = SHIFT_START_TIMES.get(shift_code, time(7, 0))
    shift_start = datetime.combine(report_date, start_time, tzinfo=CAIRO_TZ)
    shift_end = shift_start + timedelta(hours=8)
    effective_grace = int(grace_hours) if grace_hours is not None else 2
    window_end = shift_end + timedelta(hours=effective_grace)
    return shift_start, shift_end, window_end


def is_within_shift_window(shift_code, now=None, grace_hours=2, report_date=None):
    """
    Checks whether `now` (in Cairo timezone) falls within the shift window
    plus the allowed grace period (default 2 hours) after the shift ends.
    If ENFORCE_SHIFT_HOURS setting is False, returns True.
    """
    if not getattr(settings, "ENFORCE_SHIFT_HOURS", True):
        return True
    if not shift_code:
        return False

    now_dt = get_cairo_time(now)
    effective_grace = int(grace_hours) if grace_hours is not None else 2

    if report_date is not None:
        start_dt, _, end_dt = get_shift_range(shift_code, report_date, effective_grace)
        if start_dt <= now_dt <= end_dt:
            return True
        # For night shift, report_date might be calendar day of handover morning
        if shift_code == User.Shift.THIRD:
            alt_start, _, alt_end = get_shift_range(shift_code, report_date - timedelta(days=1), effective_grace)
            if alt_start <= now_dt <= alt_end:
                return True
        return False

    # Check against shift window starting today or yesterday
    current_date = now_dt.date()
    for d in (current_date, current_date - timedelta(days=1)):
        start_dt, _, end_dt = get_shift_range(shift_code, d, effective_grace)
        if start_dt <= now_dt <= end_dt:
            return True
    return False


def get_user_effective_shift(user, day=None):
    """
    Returns the effective shift of a user for a given day,
    taking weekly shift rotation into account if active for the factory.
    """
    if not user or not getattr(user, "shift", None):
        return None
    try:
        from production.shift_rotation import effective_shift
        return effective_shift(user, day)
    except Exception:
        return getattr(user, "shift", None)


def format_window_end_time(shift_code, report_date=None, grace_hours=2):
    """
    Returns a human-readable end time for the allowed window (shift + grace).
    e.g. '5:00 م'
    """
    day = report_date or timezone.localdate()
    _, _, window_end = get_shift_range(shift_code, day, grace_hours)
    hour = window_end.hour
    minute = window_end.minute
    period = "ص" if hour < 12 else "م"
    hour_12 = hour % 12
    if hour_12 == 0:
        hour_12 = 12
    minute_str = f":{minute:02d}" if minute != 0 else ":00"
    return f"{hour_12}{minute_str} {period}"


def get_shift_window_display(shift_code, grace_hours=2):
    """
    Returns human-readable shift window description including hours and grace period.
    """
    info = SHIFT_WINDOWS.get(shift_code)
    if not info:
        return ""
    grace = int(grace_hours) if grace_hours is not None else 2
    end_str = format_window_end_time(shift_code, grace_hours=grace)
    return f"{info['name']} ({info['hours_display']} + {grace} ساعة سماحية حتى {end_str})"
