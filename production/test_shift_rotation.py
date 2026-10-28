from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from factories.models import Factory
from production.handover import receiver_for
from production.models import FactoryShiftRotation, ProductionShiftReport
from production.shift_rotation import effective_shift, week_start


class WeeklyShiftRotationTests(TestCase):
    def setUp(self):
        self.factory, _ = Factory.objects.get_or_create(code="F1", defaults={"name": "مصنع 1"})
        self.supervisors = [
            User.objects.create_user(
                phone=f"0109999000{index}", password="StrongPass!123",
                name=f"مشرف {index}", factory=self.factory,
                role=User.Role.PRODUCTION_SUPERVISOR, shift=shift,
            )
            for index, shift in enumerate(("FIRST", "SECOND", "THIRD"), 1)
        ]
        self.friday = week_start(timezone.localdate(), 4)

    def test_friday_rotation_follows_configured_order_for_all_three_supervisors(self):
        rotation = FactoryShiftRotation.objects.create(
            factory=self.factory, first_shift="FIRST", second_shift="THIRD",
            third_shift="SECOND", week_starts_on=4, effective_from=self.friday,
        )
        expected = [
            ("FIRST", "SECOND", "THIRD"),
            ("THIRD", "FIRST", "SECOND"),
            ("SECOND", "THIRD", "FIRST"),
            ("FIRST", "SECOND", "THIRD"),
        ]
        for week, week_shifts in enumerate(expected):
            day = self.friday + timedelta(days=7 * week)
            self.assertEqual(tuple(effective_shift(user, day, rotation) for user in self.supervisors), week_shifts)
        self.assertEqual(receiver_for(self.supervisors[0], self.factory, self.friday), self.supervisors[2])

    def test_dashboard_saves_rotation_and_bootstrap_uses_current_week(self):
        admin = User.objects.create_superuser("01099990009", "StrongPass!123")
        self.client.force_login(admin)
        response = self.client.post(reverse("production:handover_routes") + f"?factory={self.factory.id}", {
            "action": "rotation", "first_shift": "FIRST", "second_shift": "THIRD",
            "third_shift": "SECOND", "week_starts_on": "4",
            "effective_from": (self.friday - timedelta(days=7)).isoformat(),
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(FactoryShiftRotation.objects.filter(factory=self.factory).exists())
        users_page = self.client.get(reverse("dashboard:users"))
        displayed_user = next(user for user in users_page.context["users"] if user.pk == self.supervisors[0].pk)
        self.assertEqual(displayed_user.current_shift_display, dict(User.Shift.choices)["THIRD"])

        api = APIClient()
        api.force_authenticate(user=self.supervisors[0])
        bootstrap = api.get(reverse("production-api:bootstrap"))
        self.assertEqual(bootstrap.status_code, 200)
        self.assertEqual(bootstrap.data["user"]["shift"], "THIRD")
        self.assertEqual(bootstrap.data["user"]["next_shift_supervisor"]["id"], self.supervisors[2].id)

        payload = {
            "client_report_id": "2a7e3ecb-17da-40b8-8738-b5243e885ca5",
            "report_date": timezone.localdate().isoformat(), "status": "DRAFT",
        }
        wrong_shift = api.post(reverse("production-api:sync-shift-reports"), {**payload, "shift": "FIRST"}, format="json")
        self.assertEqual(wrong_shift.status_code, 403)
        correct_shift = api.post(reverse("production-api:sync-shift-reports"), {**payload, "shift": "THIRD"}, format="json")
        self.assertEqual(correct_shift.status_code, 200, correct_shift.data)
        self.assertEqual(ProductionShiftReport.objects.get(factory=self.factory).shift, "THIRD")

    def test_dashboard_rejects_repeated_shift_in_rotation(self):
        admin = User.objects.create_superuser("01099990009", "StrongPass!123")
        self.client.force_login(admin)
        response = self.client.post(reverse("production:handover_routes") + f"?factory={self.factory.id}", {
            "action": "rotation", "first_shift": "FIRST", "second_shift": "FIRST",
            "third_shift": "THIRD", "week_starts_on": "4",
            "effective_from": self.friday.isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "اختر كل وردية مرة واحدة")
        self.assertFalse(FactoryShiftRotation.objects.filter(factory=self.factory).exists())

    def test_completed_report_goes_to_next_shift_in_configured_order(self):
        FactoryShiftRotation.objects.create(
            factory=self.factory, first_shift="FIRST", second_shift="THIRD",
            third_shift="SECOND", week_starts_on=4, effective_from=self.friday,
        )
        api = APIClient()
        api.force_authenticate(user=self.supervisors[0])
        response = api.post(reverse("production-api:sync-shift-reports"), {
            "client_report_id": "41028e37-8313-420c-938d-df2f70a7b055",
            "report_date": self.friday.isoformat(), "shift": "FIRST",
            "status": "PENDING_HANDOVER", "completed_at_device": timezone.now().isoformat(),
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        report = ProductionShiftReport.objects.get(factory=self.factory)
        self.assertEqual(report.handover_to_supervisor, self.supervisors[2])
