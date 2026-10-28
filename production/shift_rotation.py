from datetime import timedelta

from django.utils import timezone

from accounts.models import User
from .models import FactoryShiftRotation


DEFAULT_ORDER = ("FIRST", "SECOND", "THIRD")


def rotation_for(factory):
    if not factory:
        return None
    return FactoryShiftRotation.objects.filter(factory=factory).first()


def week_start(day, weekday):
    return day - timedelta(days=(day.weekday() - weekday) % 7)


def shift_for_base(base_shift, day, rotation=None):
    if not base_shift:
        return None
    if not rotation:
        return base_shift
    order = rotation.shift_order
    anchor = week_start(rotation.effective_from, rotation.week_starts_on)
    current = week_start(day, rotation.week_starts_on)
    weeks = max(0, (current - anchor).days // 7)
    return order[(order.index(base_shift) + weeks) % 3]


def effective_shift(user, day=None, rotation=None):
    day = day or timezone.localdate()
    if rotation is None:
        rotation = rotation_for(user.factory)
    return shift_for_base(user.shift, day, rotation)


def next_shift_for(user, day=None, rotation=None):
    day = day or timezone.localdate()
    if rotation is None:
        rotation = rotation_for(user.factory)
    current = shift_for_base(user.shift, day, rotation)
    if not current:
        return None
    order = rotation.shift_order if rotation else DEFAULT_ORDER
    return order[(order.index(current) + 1) % 3]


def next_supervisor_for(user, factory, day=None, rotation=None):
    day = day or timezone.localdate()
    if rotation is None:
        rotation = rotation_for(factory)
    next_shift = next_shift_for(user, day, rotation)
    if not next_shift:
        return None
    candidates = User.objects.filter(
        factory=factory, is_active=True,
        role__in=[User.Role.PRODUCTION_SUPERVISOR, User.Role.GENERAL_SUPERVISOR],
    ).exclude(pk=user.pk).order_by("pk")
    return next((candidate for candidate in candidates
                 if shift_for_base(candidate.shift, day, rotation) == next_shift), None)
