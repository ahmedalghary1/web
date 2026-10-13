import uuid
from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from accounts.models import User
from factories.models import Factory
from assets.models import Asset
from .models import SupervisorHandoverRoute, ProductionShiftReport, MachineProductionEntry, ProductionStoppage


class HandoverWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory.objects.create(name="التسليم", code="HANDOVER")
        cls.users = [User.objects.create_user(phone=f"review{i}", name=f"مشرف {i}", factory=cls.factory, role="PRODUCTION_SUPERVISOR", shift=shift) for i, shift in enumerate(["FIRST", "SECOND", "THIRD"])]
        cls.admin = User.objects.create_superuser(phone="review-admin")
        cls.other_factory = Factory.objects.create(name="آخر", code="OTHER-HANDOVER")
        cls.outsider = User.objects.create_user(phone="outside", factory=cls.other_factory, role="PRODUCTION_SUPERVISOR")
        cls.asset = Asset.objects.create(factory=cls.factory, asset_code="R1", asset_type=Asset.Type.REGULAR_MACHINE)

    def setUp(self):
        self.client = APIClient()
        self.sender, self.receiver, self.third = self.users
        # Deliberately differs from the automatic next-shift order.
        SupervisorHandoverRoute.objects.create(supervisor=self.sender, receiver=self.third)

    def report(self, **kwargs):
        data = dict(factory=self.factory, supervisor=self.sender, shift="FIRST", report_date=timezone.localdate(), status="PENDING_HANDOVER", completed_at_device=timezone.now(), handover_to_supervisor=self.third)
        data.update(kwargs)
        return ProductionShiftReport.objects.create(**data)

    def payload(self, **kwargs):
        data = dict(client_report_id=str(uuid.uuid4()), shift="FIRST", report_date=str(timezone.localdate()), status="DRAFT")
        data.update(kwargs)
        return data

    def sync(self, user, **kwargs):
        self.client.force_authenticate(user)
        return self.client.post(reverse("production-api:sync-shift-reports"), self.payload(**kwargs), format="json")

    def decide(self, user, report, decision="ACCEPT", notes=""):
        self.client.force_authenticate(user)
        return self.client.post(reverse("production-api:confirm-handover"), dict(client_report_id=str(report.client_report_id), decision=decision, handover_notes=notes), format="json")

    def test_explicit_route_and_full_report_only_for_recipient(self):
        result = self.sync(self.sender, status="PENDING_HANDOVER", completed_at_device=timezone.now().isoformat(), entries=[dict(asset_id=self.asset.pk, final_production_weight_kg=25)], stoppages=[dict(stoppage_type="OTHER", description="عطل", duration_minutes=15, action_taken="إصلاح")])
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data["handover_to_supervisor"], self.third.pk)
        for user, expected in [(self.receiver, False), (self.third, True)]:
            self.client.force_authenticate(user)
            data = self.client.get(reverse("production-api:bootstrap")).data
            self.assertEqual(data["pending_handover"] is not None, expected)
            if expected:
                self.assertEqual(data["pending_handover"]["machine_entries"][0]["final_production_weight_kg"], 25)
                self.assertEqual(data["pending_handover"]["stoppages"][0]["description"], "عطل")

    def test_reject_requires_reason_and_unlocks_next_report(self):
        report = self.report()
        self.assertEqual(self.sync(self.third, shift="THIRD").status_code, 409)
        for notes in ["", "   "]:
            self.assertEqual(self.decide(self.third, report, "REJECT", notes).status_code, 400)
        self.assertEqual(self.decide(self.third, report, "REJECT", "اختلاف الكمية").status_code, 200)
        report.refresh_from_db()
        timestamp = report.handover_confirmed_at
        self.assertEqual((report.status, report.handover_notes), ("REJECTED", "اختلاف الكمية"))
        self.assertEqual(self.decide(self.third, report, "REJECT", "اختلاف الكمية").status_code, 200)
        report.refresh_from_db()
        self.assertEqual(report.handover_confirmed_at, timestamp)
        self.assertEqual(self.decide(self.third, report).status_code, 400)
        self.assertEqual(self.sync(self.third, shift="THIRD").status_code, 200)

    def test_accept_and_permissions_and_immutable_submitted_report(self):
        report = self.report(general_notes="أصلي")
        for user in [self.sender, self.receiver, self.admin, self.outsider]:
            self.assertIn(self.decide(user, report).status_code, [403, 404])
        self.assertEqual(self.sync(self.receiver, client_report_id=str(report.client_report_id)).status_code, 403)
        self.assertEqual(self.sync(self.sender, client_report_id=str(report.client_report_id), general_notes="تغيير").status_code, 200)
        report.refresh_from_db()
        self.assertEqual(report.general_notes, "أصلي")
        self.assertEqual(self.decide(self.third, report).status_code, 200)
        self.assertEqual(self.sync(self.third, shift="THIRD").status_code, 200)

    def test_oldest_pending_first_and_no_status_forgery(self):
        first = self.report(report_date=timezone.localdate() - timedelta(days=2))
        self.report()
        self.client.force_authenticate(self.third)
        data = self.client.get(reverse("production-api:bootstrap")).data
        self.assertEqual(data["pending_handover"]["id"], first.pk)
        self.decide(self.third, first)
        self.assertEqual(self.sync(self.third, shift="THIRD").status_code, 409)
        self.assertEqual(self.sync(self.receiver, shift="SECOND", status="CONFIRMED").status_code, 400)
        self.assertEqual(self.sync(self.receiver, shift="SECOND", status="PENDING_HANDOVER", completed_at_device=timezone.now().isoformat()).status_code, 400)

    def test_dashboard_route_validation_rerouting_and_review(self):
        report = self.report()
        url = reverse("production:handover_routes") + f"?factory={self.factory.pk}"
        self.client.force_login(self.sender)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.admin)
        for target in [self.sender, self.outsider]:
            response = self.client.post(url, {"supervisor": self.sender.pk, "receiver": target.pk})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["form"].errors)
        result = self.client.post(url, {"supervisor": self.sender.pk, "receiver": self.receiver.pk})
        self.assertEqual(result.status_code, 302)
        report.refresh_from_db()
        self.assertEqual(report.handover_to_supervisor_id, self.receiver.pk)
        self.client.force_login(self.receiver)
        review_url = reverse("production:confirm-handover", args=[report.pk])
        self.client.post(review_url, {"decision": "REJECT", "handover_notes": ""})
        report.refresh_from_db()
        self.assertEqual(report.status, "PENDING_HANDOVER")
        self.client.post(review_url, {"decision": "REJECT", "handover_notes": "البيانات غير مطابقة"})
        detail = self.client.get(reverse("production:report_detail", args=[report.pk]))
        self.assertContains(detail, "غير مقبول")
        self.assertContains(detail, "البيانات غير مطابقة")
