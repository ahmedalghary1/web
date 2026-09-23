import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from accounts.models import User
from assets.models import Asset
from factories.models import Factory
from maintenance.models import MaintenanceReport
from maintenance.services.cycle import MaintenanceCycleService

CAIRO = ZoneInfo("Africa/Cairo")
class CycleServiceTests(TestCase):
    def setUp(self):
        self.f1 = Factory.objects.get(code="F1"); self.f2 = Factory.objects.get(code="F2"); self.f3 = Factory.objects.get(code="F3")
        self.u1 = User.objects.create_user("01000000001", "StrongPass!123", factory=self.f1); self.u2 = User.objects.create_user("01000000002", "StrongPass!123", factory=self.f2)
    def asset(self, factory, kind, code, order): return Asset.objects.create(factory=factory, asset_type=kind, asset_code=code, sequence_order=order)
    def workdays(self, count):
        day = timezone.localdate(); days = []
        while len(days) < count:
            if MaintenanceCycleService.is_maintenance_day(day): days.append(day)
            day -= timedelta(days=1)
        return list(reversed(days))
    def payload(self, asset, date, client_id=None):
        start = datetime.combine(date, datetime.min.time(), tzinfo=CAIRO) + timedelta(hours=8); template = MaintenanceCycleService.template_for(asset)
        answers = [{"checklist_item_id": i.id, "checked": i.id % 2 == 0, "note": ""} for s in template.sections.all() for i in s.items.all() if i.is_active]
        return {"client_report_id": client_id or uuid.uuid4(), "asset_id": asset.id, "report_date": date, "started_at_device": start, "completed_at_device": start+timedelta(minutes=20), "last_modified_at_device": start+timedelta(minutes=20), "answers": answers}
    def complete(self, user, asset, date): return MaintenanceCycleService.upsert_report(user, self.payload(asset, date))
    def test_factory_1_regular_then_press_then_wraps(self):
        r1=self.asset(self.f1,Asset.Type.REGULAR_MACHINE,"R-A",1); r2=self.asset(self.f1,Asset.Type.REGULAR_MACHINE,"R-B",2); p1=self.asset(self.f1,Asset.Type.PRESS,"P-A",1); days=self.workdays(4)
        self.assertEqual(MaintenanceCycleService.current_asset(self.f1,days[0])[0],r1); self.complete(self.u1,r1,days[0]); self.assertEqual(MaintenanceCycleService.current_asset(self.f1,days[1])[0],r2); self.complete(self.u1,r2,days[1]); self.assertEqual(MaintenanceCycleService.current_asset(self.f1,days[2])[0],p1); self.complete(self.u1,p1,days[2]); self.assertEqual(MaintenanceCycleService.current_asset(self.f1,days[3])[0],r1)
    def test_factory_3_uses_regular_then_press(self):
        r=self.asset(self.f3,Asset.Type.REGULAR_MACHINE,"R3",1); p=self.asset(self.f3,Asset.Type.PRESS,"P3",1); user=User.objects.create_user("01000000003","StrongPass!123",factory=self.f3); days=self.workdays(2); self.complete(user,r,days[0]); self.assertEqual(MaintenanceCycleService.current_asset(self.f3,days[1])[0],p)
    def test_factory_2_regular_then_spring_then_wraps(self):
        r=self.asset(self.f2,Asset.Type.REGULAR_MACHINE,"R2",1); s=self.asset(self.f2,Asset.Type.SPRING_MACHINE,"S2",1); days=self.workdays(3); self.complete(self.u2,r,days[0]); self.assertEqual(MaintenanceCycleService.current_asset(self.f2,days[1])[0],s); self.complete(self.u2,s,days[1]); self.assertEqual(MaintenanceCycleService.current_asset(self.f2,days[2])[0],r)
    def test_does_not_advance_without_report(self):
        first=self.asset(self.f1,Asset.Type.REGULAR_MACHINE,"A",1); self.asset(self.f1,Asset.Type.REGULAR_MACHINE,"B",2); days=self.workdays(2); self.assertEqual(MaintenanceCycleService.current_asset(self.f1,days[0])[0],first); self.assertEqual(MaintenanceCycleService.current_asset(self.f1,days[1])[0],first)
    def test_friday_has_no_task_and_pending_asset_resumes_after_it(self):
        first=self.asset(self.f1,Asset.Type.REGULAR_MACHINE,"A",1); self.asset(self.f1,Asset.Type.REGULAR_MACHINE,"B",2)
        friday = timezone.localdate()
        while friday.weekday() != 4: friday -= timedelta(days=1)
        thursday, saturday = friday-timedelta(days=1), friday+timedelta(days=1)
        self.assertEqual(MaintenanceCycleService.current_asset(self.f1,thursday)[0],first)
        self.assertIsNone(MaintenanceCycleService.current_asset(self.f1,friday)[0])
        self.assertEqual(MaintenanceCycleService.current_asset(self.f1,saturday)[0],first)
        self.assertEqual(self.complete(self.u1,first,friday).status,"rejected")
    def test_manual_selection_persists_until_completed_then_advances(self):
        a=self.asset(self.f1,Asset.Type.REGULAR_MACHINE,"A",1); b=self.asset(self.f1,Asset.Type.REGULAR_MACHINE,"B",2); c=self.asset(self.f1,Asset.Type.REGULAR_MACHINE,"C",3); days=self.workdays(2)
        MaintenanceCycleService.select_current_asset(self.f1,c,self.u1,days[0])
        self.assertEqual(MaintenanceCycleService.current_asset(self.f1,days[1])[0],c)
        self.complete(self.u1,c,days[1])
        next_day=days[1]+timedelta(days=1)
        while not MaintenanceCycleService.is_maintenance_day(next_day): next_day += timedelta(days=1)
        self.assertEqual(MaintenanceCycleService.current_asset(self.f1,next_day)[0],a)
    def test_duplicate_day_is_rejected_and_client_id_is_idempotent(self):
        first=self.asset(self.f1,Asset.Type.REGULAR_MACHINE,"A",1); day=timezone.localdate(); client=uuid.uuid4(); payload=self.payload(first,day,client); self.assertEqual(MaintenanceCycleService.upsert_report(self.u1,payload).status,"synced"); self.assertEqual(MaintenanceCycleService.upsert_report(self.u1,payload).status,"already_synced"); self.assertEqual(MaintenanceReport.objects.count(),1); self.assertEqual(MaintenanceCycleService.upsert_report(self.u1,self.payload(first,day)).status,"conflict")
    def test_historical_report_is_locked_but_delayed_sync_is_accepted(self):
        first=self.asset(self.f1,Asset.Type.REGULAR_MACHINE,"A",1); day=self.workdays(3)[0]; result=self.complete(self.u1,first,day); self.assertEqual(result.status,"synced"); self.assertTrue(result.report.effectively_locked); self.assertEqual(MaintenanceCycleService.upsert_report(self.u1,self.payload(first,day,result.report.client_report_id)).status,"already_synced")
    def test_reorder_preserves_current(self):
        a=self.asset(self.f1,Asset.Type.REGULAR_MACHINE,"A",1); b=self.asset(self.f1,Asset.Type.REGULAR_MACHINE,"B",2); c=self.asset(self.f1,Asset.Type.REGULAR_MACHINE,"C",3); today=timezone.localdate(); self.assertEqual(MaintenanceCycleService.current_asset(self.f1,today)[0],a); MaintenanceCycleService.reorder(self.f1,[c.id,a.id,b.id]); self.assertEqual(MaintenanceCycleService.current_asset(self.f1,today)[0],a)
    def test_archived_current_moves_to_next_active(self):
        a=self.asset(self.f1,Asset.Type.REGULAR_MACHINE,"A",1); b=self.asset(self.f1,Asset.Type.REGULAR_MACHINE,"B",2); today=timezone.localdate(); MaintenanceCycleService.current_asset(self.f1,today); a.is_archived=True; a.is_active=False; a.save(); self.assertEqual(MaintenanceCycleService.current_asset(self.f1,today)[0],b)
    def test_invalid_factory_asset_type_is_blocked(self):
        with self.assertRaises(ValidationError): self.asset(self.f2,Asset.Type.PRESS,"NO",1)
    def test_automatic_order_appends_within_type(self):
        self.asset(self.f1,Asset.Type.PRESS,"P1",3); p2=Asset.objects.create(factory=self.f1,asset_type=Asset.Type.PRESS,asset_code="P2"); self.assertEqual(p2.sequence_order,4)
    def test_emergency_maintenance_items_saved_and_retrieved(self):
        first = self.asset(self.f1, Asset.Type.REGULAR_MACHINE, "A", 1); press = self.asset(self.f1, Asset.Type.PRESS, "P1", 2); day = timezone.localdate(); payload = self.payload(first, day)
        payload["emergency_items"] = [{"asset_id": press.id, "issue_description": "تسريب زيت في الصمام", "responsible_person": "م. أحمد", "notes": "تم استبدال الأويل سيل"}]
        res = MaintenanceCycleService.upsert_report(self.u1, payload)
        self.assertEqual(res.status, "synced")
        self.assertEqual(res.report.emergency_items.count(), 1)
        em = res.report.emergency_items.first()
        self.assertEqual(em.asset_id, press.id); self.assertEqual(em.issue_description, "تسريب زيت في الصمام"); self.assertEqual(em.responsible_person, "م. أحمد")

    def test_personnel_fields_saved_and_serialized(self):
        from api.serializers import ReportSerializer
        first = self.asset(self.f1, Asset.Type.REGULAR_MACHINE, "A", 1)
        day = timezone.localdate()
        payload = self.payload(first, day)
        payload["cleaner_name"] = "محمد حسن"
        payload["mechanical_technician"] = "أحمد إبراهيم"
        payload["electrical_technician"] = "محمود السيد"
        payload["maintenance_manager"] = "م. خالد عبد الرحمن"
        res = MaintenanceCycleService.upsert_report(self.u1, payload)
        self.assertEqual(res.status, "synced")
        report = res.report
        self.assertEqual(report.cleaner_name, "محمد حسن")
        self.assertEqual(report.mechanical_technician, "أحمد إبراهيم")
        self.assertEqual(report.electrical_technician, "محمود السيد")
        self.assertEqual(report.maintenance_manager, "م. خالد عبد الرحمن")

        # Check serialization output
        serialized = ReportSerializer(report).data
        self.assertEqual(serialized["cleaner_name"], "محمد حسن")
        self.assertEqual(serialized["mechanical_technician"], "أحمد إبراهيم")
        self.assertEqual(serialized["electrical_technician"], "محمود السيد")
        self.assertEqual(serialized["maintenance_manager"], "م. خالد عبد الرحمن")

    def test_monthly_report_view_renders_kpis_and_machines(self):
        from django.urls import reverse
        admin = User.objects.create_superuser("01099999999", "AdminPass!123", factory=self.f1)
        first = self.asset(self.f1, Asset.Type.REGULAR_MACHINE, "R-REP-1", 1)
        day = timezone.localdate()
        payload = self.payload(first, day)
        payload["cleaner_name"] = "علي النجار"
        payload["mechanical_technician"] = "حسام عثمان"
        payload["emergency_items"] = [{"asset_id": first.id, "issue_description": "سخونة مفرطة بالمحرك", "responsible_person": "حسام", "notes": "تم تبريد وتغيير الزيت"}]
        res = MaintenanceCycleService.upsert_report(self.u1, payload)
        self.assertEqual(res.status, "synced")

        self.client.force_login(admin)
        url = reverse("dashboard:monthly_report")
        response = self.client.get(url, {"period": "current_month"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "تقرير الصيانة الشهري والدوري الشامل")
        self.assertContains(response, "R-REP-1")
        self.assertContains(response, "سخونة مفرطة بالمحرك")
        self.assertContains(response, "علي النجار")
        self.assertContains(response, "حسام عثمان")

        # Test context KPIs
        context = response.context
        self.assertGreaterEqual(context["total_reports"], 1)
        self.assertGreaterEqual(len(context["machines_summary"]), 1)
        self.assertGreaterEqual(len(context["emergency_incidents"]), 1)
        self.assertEqual(context["emergency_incidents"][0]["issue_description"], "سخونة مفرطة بالمحرك")

    def test_export_monthly_report_csv(self):
        from django.urls import reverse
        admin = User.objects.create_superuser("01088888888", "AdminPass!123", factory=self.f1)
        first = self.asset(self.f1, Asset.Type.REGULAR_MACHINE, "R-CSV-1", 1)
        day = timezone.localdate()
        payload = self.payload(first, day)
        payload["cleaner_name"] = "سعيد عامل"
        MaintenanceCycleService.upsert_report(self.u1, payload)

        self.client.force_login(admin)
        url = reverse("dashboard:export_monthly_report_csv")
        response = self.client.get(url, {"period": "current_month"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8-sig")
        self.assertTrue(response.has_header("Content-Disposition"))
        content = response.content.decode("utf-8-sig")
        self.assertIn("تاريخ التقرير", content)
        self.assertIn("R-CSV-1", content)
        self.assertIn("سعيد عامل", content)

