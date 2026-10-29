from datetime import time, datetime
from zoneinfo import ZoneInfo
from django.conf import settings
from django.utils import timezone
from accounts.models import User

CAIRO_TZ = ZoneInfo("Africa/Cairo")

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
    Returns the current datetime in Africa/Cairo timezone.
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


def is_within_shift_window(shift_code, now=None):
    """
    Checks whether `now` (in Cairo timezone) falls within the 8 hours of `shift_code`.
    If ENFORCE_SHIFT_HOURS setting is False, returns True (useful for tests or overrides).
    """
    if not getattr(settings, "ENFORCE_SHIFT_HOURS", True):
        return True
    if not shift_code:
        return False
    return get_current_shift_by_time(now) == shift_code


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


def get_shift_window_display(shift_code):
    """
    Returns human-readable shift window description (hours and name).
    """
    info = SHIFT_WINDOWS.get(shift_code)
    if not info:
        return ""
    return f"{info['name']} ({info['hours_display']})"

