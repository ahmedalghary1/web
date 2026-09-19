from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from assets.models import Asset
from factories.models import Factory
from maintenance.models import MaintenanceReport


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
