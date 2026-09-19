from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from assets.models import Asset
from factories.models import Factory
from maintenance.models import FactoryMaintenanceState, MaintenanceReport


class DashboardReportLinkTests(TestCase):
    def setUp(self):
        factory = Factory.objects.get(code="F1")
        asset = Asset.objects.create(
            factory=factory,
            asset_type=Asset.Type.REGULAR_MACHINE,
            asset_code="REPORT-LINK",
            sequence_order=1,
        )
        supervisor = User.objects.create_user(
            "01000000991",
            "StrongPass!123",
            factory=factory,
        )
        admin = User.objects.create_superuser("01000000992", "StrongPass!123")
        now = timezone.now()
        self.report = MaintenanceReport.objects.create(
            factory=factory,
            asset=asset,
            supervisor=supervisor,
            report_date=timezone.localdate(),
            started_at_device=now - timedelta(minutes=5),
            completed_at_device=now,
            last_modified_at_device=now,
        )
        self.client.force_login(admin)

    def test_report_list_renders_detail_link(self):
        response = self.client.get(reverse("dashboard:reports"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("dashboard:report_detail", args=[self.report.pk]))

    def test_home_renders_detail_link(self):
        response = self.client.get(reverse("dashboard:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("dashboard:report_detail", args=[self.report.pk]))

    def test_completed_daily_report_cannot_be_reassigned(self):
        other = Asset.objects.create(factory=self.report.factory, asset_type=Asset.Type.REGULAR_MACHINE, asset_code="OTHER-ASSET", sequence_order=2)
        response = self.client.post(reverse("dashboard:daily-select-asset", args=[self.report.factory_id]), {"asset_id": other.id}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.report.refresh_from_db()
        self.assertNotEqual(self.report.asset_id, other.id)
        self.assertContains(response, "تم إكمال تقرير هذا اليوم بالفعل")

    def test_admin_can_reassign_unstarted_daily_task(self):
        factory = Factory.objects.get(code="F2")
        first = Asset.objects.create(factory=factory, asset_type=Asset.Type.REGULAR_MACHINE, asset_code="F2-FIRST", sequence_order=1)
        selected = Asset.objects.create(factory=factory, asset_type=Asset.Type.SPRING_MACHINE, asset_code="F2-SELECTED", sequence_order=1)
        response = self.client.post(reverse("dashboard:daily-select-asset", args=[factory.id]), {"asset_id": selected.id}, follow=True)
        self.assertEqual(response.status_code, 200)
        state = FactoryMaintenanceState.objects.get(factory=factory)
        self.assertEqual(state.current_asset_id, selected.id)
        self.assertIsNotNone(state.manual_selected_by_id)
        self.assertContains(response, "تم تعيين الماكينة")
