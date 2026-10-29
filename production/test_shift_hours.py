import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from accounts.shifts import (
    CAIRO_TZ,
    SHIFT_WINDOWS,
    get_current_shift_by_time,
    is_within_shift_window,
    get_user_effective_shift,
)
from assets.models import Asset
from dashboard.forms import SupervisorForm
from factories.models import Factory
from maintenance.models import MaintenanceReport
from maintenance.services.cycle import MaintenanceCycleService
from production.models import ProductionShiftReport


@override_settings(ENFORCE_SHIFT_HOURS=True)
class ShiftHoursLogicTests(TestCase):
    """Test 8-hour shift calculation and window checking functions."""

    def test_shift_by_time_partition(self):
        day = timezone.localdate()
        # Morning shift (07:00 - 15:00)
        self.assertEqual(get_current_shift_by_time(datetime.combine(day, time(7, 0), tzinfo=CAIRO_TZ)), User.Shift.FIRST)
        self.assertEqual(get_current_shift_by_time(datetime.combine(day, time(10, 30), tzinfo=CAIRO_TZ)), User.Shift.FIRST)
        self.assertEqual(get_current_shift_by_time(datetime.combine(day, time(14, 59, 59), tzinfo=CAIRO_TZ)), User.Shift.FIRST)

        # Evening shift (15:00 - 23:00)
        self.assertEqual(get_current_shift_by_time(datetime.combine(day, time(15, 0), tzinfo=CAIRO_TZ)), User.Shift.SECOND)
        self.assertEqual(get_current_shift_by_time(datetime.combine(day, time(19, 0), tzinfo=CAIRO_TZ)), User.Shift.SECOND)
        self.assertEqual(get_current_shift_by_time(datetime.combine(day, time(22, 59, 59), tzinfo=CAIRO_TZ)), User.Shift.SECOND)

        # Night shift (23:00 - 07:00)
        self.assertEqual(get_current_shift_by_time(datetime.combine(day, time(23, 0), tzinfo=CAIRO_TZ)), User.Shift.THIRD)
        self.assertEqual(get_current_shift_by_time(datetime.combine(day, time(23, 45), tzinfo=CAIRO_TZ)), User.Shift.THIRD)
        self.assertEqual(get_current_shift_by_time(datetime.combine(day, time(0, 0), tzinfo=CAIRO_TZ)), User.Shift.THIRD)
        self.assertEqual(get_current_shift_by_time(datetime.combine(day, time(3, 15), tzinfo=CAIRO_TZ)), User.Shift.THIRD)
        self.assertEqual(get_current_shift_by_time(datetime.combine(day, time(6, 59, 59), tzinfo=CAIRO_TZ)), User.Shift.THIRD)

    def test_is_within_shift_window(self):
        day = timezone.localdate()
        morning_time = datetime.combine(day, time(9, 0), tzinfo=CAIRO_TZ)
        evening_time = datetime.combine(day, time(17, 0), tzinfo=CAIRO_TZ)
        night_time = datetime.combine(day, time(2, 0), tzinfo=CAIRO_TZ)

        # Morning
        self.assertTrue(is_within_shift_window(User.Shift.FIRST, morning_time))
        self.assertFalse(is_within_shift_window(User.Shift.FIRST, evening_time))
        self.assertFalse(is_within_shift_window(User.Shift.FIRST, night_time))

        # Evening
        self.assertFalse(is_within_shift_window(User.Shift.SECOND, morning_time))
        self.assertTrue(is_within_shift_window(User.Shift.SECOND, evening_time))
        self.assertFalse(is_within_shift_window(User.Shift.SECOND, night_time))

        # Night
        self.assertFalse(is_within_shift_window(User.Shift.THIRD, morning_time))
        self.assertFalse(is_within_shift_window(User.Shift.THIRD, evening_time))
        self.assertTrue(is_within_shift_window(User.Shift.THIRD, night_time))


@override_settings(ENFORCE_SHIFT_HOURS=True)
class ProductionShiftHoursEnforcementTests(TestCase):
    """Test production reports 8-hour window and shift validation."""

    def setUp(self):
        self.factory, _ = Factory.objects.get_or_create(code="F1", defaults={"name": "مصنع 1"})
        self.asset = Asset.objects.create(
            factory=self.factory, asset_type=Asset.Type.REGULAR_MACHINE,
            asset_code="M-01", sequence_order=1
        )
        self.morning_sup = User.objects.create_user(
            phone="01011110001", password="StrongPass!123", name="مشرف صباحي",
            factory=self.factory, role=User.Role.PRODUCTION_SUPERVISOR, shift=User.Shift.FIRST,
        )
        self.evening_sup = User.objects.create_user(
            phone="01011110002", password="StrongPass!123", name="مشرف مسائي",
            factory=self.factory, role=User.Role.PRODUCTION_SUPERVISOR, shift=User.Shift.SECOND,
        )
        self.night_sup = User.objects.create_user(
            phone="01011110003", password="StrongPass!123", name="مشرف ليلي",
            factory=self.factory, role=User.Role.PRODUCTION_SUPERVISOR, shift=User.Shift.THIRD,
        )
        self.no_shift_sup = User.objects.create_user(
            phone="01011110004", password="StrongPass!123", name="مشرف بدون وردية",
            factory=self.factory, role=User.Role.PRODUCTION_SUPERVISOR, shift=None,
        )
        self.admin = User.objects.create_superuser("01011110009", "StrongPass!123")
        self.today = timezone.localdate()

    def _sync_payload(self, shift, report_date=None, client_id=None):
        return {
            "client_report_id": str(client_id or uuid.uuid4()),
            "shift": shift,
            "report_date": str(report_date or self.today),
            "status": "DRAFT",
            "entries": [],
            "stoppages": [],
        }

    def test_supervisor_without_shift_is_rejected(self):
        client = APIClient()
        client.force_authenticate(user=self.no_shift_sup)
        res = client.post(reverse("production-api:sync-shift-reports"), self._sync_payload("FIRST"), format="json")
        self.assertEqual(res.status_code, 403)
        self.assertIn("لم يتم تحديد وردية", res.data["detail"])

    def test_supervisor_cannot_submit_report_for_different_shift(self):
        client = APIClient()
        client.force_authenticate(user=self.morning_sup)
        # Attempt to submit evening shift while assigned morning shift
        res = client.post(reverse("production-api:sync-shift-reports"), self._sync_payload("SECOND"), format="json")
        self.assertEqual(res.status_code, 403)
        self.assertIn("لا يمكن تسجيل تقرير لوردية غير الوردية المعيّنة", res.data["detail"])

    def test_morning_supervisor_allowed_during_morning_hours(self):
        client = APIClient()
        client.force_authenticate(user=self.morning_sup)
        morning_dt = datetime.combine(self.today, time(10, 0), tzinfo=CAIRO_TZ)
        with timezone.override(CAIRO_TZ):
            # Patch timezone.localtime to simulate 10:00 AM
            from unittest.mock import patch
            with patch("django.utils.timezone.localtime", return_value=morning_dt):
                res = client.post(reverse("production-api:sync-shift-reports"), self._sync_payload("FIRST"), format="json")
                self.assertEqual(res.status_code, 200)

    def test_morning_supervisor_blocked_during_evening_hours(self):
        client = APIClient()
        client.force_authenticate(user=self.morning_sup)
        evening_dt = datetime.combine(self.today, time(17, 0), tzinfo=CAIRO_TZ)
        from unittest.mock import patch
        with patch("django.utils.timezone.localtime", return_value=evening_dt):
            res = client.post(reverse("production-api:sync-shift-reports"), self._sync_payload("FIRST"), format="json")
            self.assertEqual(res.status_code, 403)
            self.assertIn("لا يمكن تسجيل أو إرسال تقرير الوردية الأولى (صباحية)", res.data["detail"])
            self.assertIn("من 7:00 صباحاً إلى 3:00 مساءً", res.data["detail"])

    def test_evening_supervisor_allowed_during_evening_hours(self):
        client = APIClient()
        client.force_authenticate(user=self.evening_sup)
        evening_dt = datetime.combine(self.today, time(18, 0), tzinfo=CAIRO_TZ)
        from unittest.mock import patch
        with patch("django.utils.timezone.localtime", return_value=evening_dt):
            res = client.post(reverse("production-api:sync-shift-reports"), self._sync_payload("SECOND"), format="json")
            self.assertEqual(res.status_code, 200)

    def test_evening_supervisor_blocked_during_night_hours(self):
        client = APIClient()
        client.force_authenticate(user=self.evening_sup)
        night_dt = datetime.combine(self.today, time(1, 0), tzinfo=CAIRO_TZ)
        from unittest.mock import patch
        with patch("django.utils.timezone.localtime", return_value=night_dt):
            res = client.post(reverse("production-api:sync-shift-reports"), self._sync_payload("SECOND"), format="json")
            self.assertEqual(res.status_code, 403)
            self.assertIn("لا يمكن تسجيل أو إرسال تقرير الوردية الثانية (مسائية)", res.data["detail"])
            self.assertIn("من 3:00 مساءً إلى 11:00 مساءً", res.data["detail"])

    def test_night_supervisor_allowed_during_night_hours(self):
        client = APIClient()
        client.force_authenticate(user=self.night_sup)
        night_dt = datetime.combine(self.today, time(2, 0), tzinfo=CAIRO_TZ)
        from unittest.mock import patch
        with patch("django.utils.timezone.localtime", return_value=night_dt):
            res = client.post(reverse("production-api:sync-shift-reports"), self._sync_payload("THIRD"), format="json")
            self.assertEqual(res.status_code, 200)

    def test_night_supervisor_blocked_during_morning_hours(self):
        client = APIClient()
        client.force_authenticate(user=self.night_sup)
        morning_dt = datetime.combine(self.today, time(11, 0), tzinfo=CAIRO_TZ)
        from unittest.mock import patch
        with patch("django.utils.timezone.localtime", return_value=morning_dt):
            res = client.post(reverse("production-api:sync-shift-reports"), self._sync_payload("THIRD"), format="json")
            self.assertEqual(res.status_code, 403)
            self.assertIn("لا يمكن تسجيل أو إرسال تقرير الوردية الثالثة (ليلية)", res.data["detail"])
            self.assertIn("من 11:00 مساءً إلى 7:00 صباحاً", res.data["detail"])

    def test_admin_can_submit_any_shift_anytime(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        evening_dt = datetime.combine(self.today, time(17, 0), tzinfo=CAIRO_TZ)
        from unittest.mock import patch
        with patch("django.utils.timezone.localtime", return_value=evening_dt):
            # Admin submitting morning shift report during evening hours
            res = client.post(reverse("production-api:sync-shift-reports"), self._sync_payload("FIRST"), format="json")
            self.assertEqual(res.status_code, 200)


@override_settings(ENFORCE_SHIFT_HOURS=True)
class MaintenanceShiftHoursEnforcementTests(TestCase):
    """Test maintenance report restricted to morning shift supervisor and morning hours."""

    def setUp(self):
        self.factory, _ = Factory.objects.get_or_create(code="F1", defaults={"name": "مصنع 1"})
        self.asset = Asset.objects.create(
            factory=self.factory, asset_type=Asset.Type.REGULAR_MACHINE,
            asset_code="M-01", sequence_order=1
        )
        self.morning_maint_sup = User.objects.create_user(
            phone="01022220001", password="StrongPass!123", name="مشرف صيانة صباحي",
            factory=self.factory, role=User.Role.MAINTENANCE_SUPERVISOR, shift=User.Shift.FIRST,
        )
        self.evening_sup = User.objects.create_user(
            phone="01022220002", password="StrongPass!123", name="مشرف مسائي",
            factory=self.factory, role=User.Role.PRODUCTION_SUPERVISOR, shift=User.Shift.SECOND,
        )
        self.night_sup = User.objects.create_user(
            phone="01022220003", password="StrongPass!123", name="مشرف ليلي",
            factory=self.factory, role=User.Role.PRODUCTION_SUPERVISOR, shift=User.Shift.THIRD,
        )
        self.evening_general_sup = User.objects.create_user(
            phone="01022220005", password="StrongPass!123", name="مشرف عام مسائي",
            factory=self.factory, role=User.Role.GENERAL_SUPERVISOR, shift=User.Shift.SECOND,
        )
        self.today = timezone.localdate()
        # Find next maintenance workday
        while not MaintenanceCycleService.is_maintenance_day(self.today):
            self.today -= timedelta(days=1)

    def _maint_payload(self):
        template = MaintenanceCycleService.template_for(self.asset)
        answers = [{"checklist_item_id": i.id, "checked": True, "note": ""}
                   for s in template.sections.all() for i in s.items.all() if i.is_active]
        start = datetime.combine(self.today, time(8, 0), tzinfo=CAIRO_TZ)
        return {
            "client_report_id": uuid.uuid4(),
            "asset_id": self.asset.id,
            "report_date": self.today,
            "started_at_device": start,
            "completed_at_device": start + timedelta(minutes=30),
            "last_modified_at_device": start + timedelta(minutes=30),
            "answers": answers,
        }

    def test_morning_supervisor_allowed_during_morning_hours(self):
        morning_dt = datetime.combine(self.today, time(9, 30), tzinfo=CAIRO_TZ)
        from unittest.mock import patch
        with patch("django.utils.timezone.localtime", return_value=morning_dt):
            result = MaintenanceCycleService.upsert_report(self.morning_maint_sup, self._maint_payload())
            self.assertEqual(result.status, "synced")

    def test_morning_supervisor_blocked_during_evening_hours(self):
        evening_dt = datetime.combine(self.today, time(16, 0), tzinfo=CAIRO_TZ)
        from unittest.mock import patch
        with patch("django.utils.timezone.localtime", return_value=evening_dt):
            result = MaintenanceCycleService.upsert_report(self.morning_maint_sup, self._maint_payload())
            self.assertEqual(result.status, "rejected")
            self.assertIn("لا يمكن تسجيل أو إرسال تقرير الصيانة إلا خلال ساعات الوردية الصباحية", result.reason)
            self.assertIn("من 7:00 صباحاً إلى 3:00 مساءً", result.reason)

    def test_evening_supervisor_cannot_do_maintenance(self):
        morning_dt = datetime.combine(self.today, time(10, 0), tzinfo=CAIRO_TZ)
        from unittest.mock import patch
        with patch("django.utils.timezone.localtime", return_value=morning_dt):
            result = MaintenanceCycleService.upsert_report(self.evening_sup, self._maint_payload())
            self.assertEqual(result.status, "rejected")
            self.assertIn("مشرف الوردية الصباحية فقط", result.reason)

    def test_night_supervisor_cannot_do_maintenance(self):
        night_dt = datetime.combine(self.today, time(2, 0), tzinfo=CAIRO_TZ)
        from unittest.mock import patch
        with patch("django.utils.timezone.localtime", return_value=night_dt):
            result = MaintenanceCycleService.upsert_report(self.night_sup, self._maint_payload())
            self.assertEqual(result.status, "rejected")
            self.assertIn("مشرف الوردية الصباحية فقط", result.reason)

    def test_maintenance_api_permission_denied_for_non_morning_supervisor(self):
        client = APIClient()
        client.force_authenticate(user=self.evening_general_sup)
        res = client.get("/api/v1/mobile/current-maintenance/")
        self.assertEqual(res.status_code, 403)
        self.assertIn("متاحة لمشرف الوردية الصباحية فقط", res.data["detail"])

        client.force_authenticate(user=self.evening_sup)
        res2 = client.get("/api/v1/mobile/current-maintenance/")
        self.assertEqual(res2.status_code, 403)


class SupervisorFormShiftValidationTests(TestCase):
    """Test dashboard form validations for supervisor shifts."""

    def setUp(self):
        self.factory, _ = Factory.objects.get_or_create(code="F1", defaults={"name": "مصنع 1"})

    def test_maintenance_supervisor_must_be_first_shift(self):
        # Trying to assign SECOND shift to MAINTENANCE_SUPERVISOR should fail
        form = SupervisorForm({
            "name": "مشرف صيانة",
            "phone": "01033330001",
            "role": User.Role.MAINTENANCE_SUPERVISOR,
            "factory": self.factory.id,
            "shift": User.Shift.SECOND,
            "is_active": True,
            "password": "StrongPassword!123",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("shift", form.errors)
        self.assertIn("الوردية الأولى (الصباحية", form.errors["shift"][0])

    def test_maintenance_supervisor_valid_with_first_shift(self):
        form = SupervisorForm({
            "name": "مشرف صيانة",
            "phone": "01033330002",
            "role": User.Role.MAINTENANCE_SUPERVISOR,
            "factory": self.factory.id,
            "shift": User.Shift.FIRST,
            "is_active": True,
            "password": "StrongPassword!123",
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_production_supervisor_requires_shift(self):
        form = SupervisorForm({
            "name": "مشرف إنتاج",
            "phone": "01033330003",
            "role": User.Role.PRODUCTION_SUPERVISOR,
            "factory": self.factory.id,
            "shift": "",
            "is_active": True,
            "password": "StrongPassword!123",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("shift", form.errors)
        self.assertIn("يجب تحديد الوردية", form.errors["shift"][0])

    def test_production_supervisor_can_have_second_or_third_shift(self):
        for shift in (User.Shift.FIRST, User.Shift.SECOND, User.Shift.THIRD):
            form = SupervisorForm({
                "name": f"مشرف إنتاج {shift}",
                "phone": f"010333300{shift[:2]}",
                "role": User.Role.PRODUCTION_SUPERVISOR,
                "factory": self.factory.id,
                "shift": shift,
                "is_active": True,
                "password": "StrongPassword!123",
            })
            self.assertTrue(form.is_valid(), form.errors)

