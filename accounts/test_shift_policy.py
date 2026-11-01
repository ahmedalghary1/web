from datetime import date, datetime, timedelta

from django.test import SimpleTestCase, override_settings

from accounts.shifts import CAIRO_TZ, is_within_shift_window
from production.shift_rotation import shift_for_base


@override_settings(ENFORCE_SHIFT_HOURS=True)
class ShiftWindowPolicyTests(SimpleTestCase):
    def test_report_date_is_the_shift_start_date(self):
        day = date(2026, 11, 1)
        at = lambda hour, minute=0, next_day=False: datetime.combine(
            day + timedelta(days=next_day), datetime.min.time(), tzinfo=CAIRO_TZ
        ).replace(hour=hour, minute=minute)
        self.assertTrue(is_within_shift_window("FIRST", at(7), report_date=day))
        self.assertTrue(is_within_shift_window("FIRST", at(17), report_date=day))
        self.assertFalse(is_within_shift_window("FIRST", at(17, 1), report_date=day))
        self.assertTrue(is_within_shift_window("SECOND", at(0, next_day=True), report_date=day))
        self.assertTrue(is_within_shift_window("THIRD", at(9, next_day=True), report_date=day))
        self.assertFalse(is_within_shift_window("THIRD", at(9, 1, next_day=True), report_date=day))
        self.assertFalse(is_within_shift_window("THIRD", at(2, next_day=True), report_date=day + timedelta(days=1)))

    def test_default_rotation_order(self):
        # The configured default starts on Friday 30 October 2026.
        order = ("FIRST", "THIRD", "SECOND", "FIRST")
        from production.models import FactoryShiftRotation
        rotation = FactoryShiftRotation(
            first_shift="FIRST", second_shift="THIRD", third_shift="SECOND",
            week_starts_on=4, effective_from=date(2026, 10, 30),
        )
        for week, expected in enumerate(order):
            self.assertEqual(shift_for_base("FIRST", date(2026, 10, 30) + timedelta(weeks=week), rotation), expected)
