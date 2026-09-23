import uuid
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from accounts.models import User
from factories.models import Factory
from assets.models import Asset
from production.models import (
    Product,
    MachineOperator,
    MachineProductionDefault,
    ProductionShiftReport,
    MachineProductionEntry,
    ProductionStoppage,
)

class ProductionAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.factory, _ = Factory.objects.get_or_create(code="F1", defaults={"name": "مصنع النقاء للبلاستيك"})
        
        self.supervisor1 = User.objects.create_user(
            phone="01111111111",
            password="password123",
            name="م. أحمد مشرف",
            role=User.Role.PRODUCTION_SUPERVISOR,
            factory=self.factory,
        )
        self.supervisor2 = User.objects.create_user(
            phone="01111111112",
            password="password123",
            name="م. محمود مستلم",
            role=User.Role.PRODUCTION_SUPERVISOR,
            factory=self.factory,
        )


        self.asset1 = Asset.objects.create(
            factory=self.factory,
            asset_code="M-01",
            asset_type=Asset.Type.REGULAR_MACHINE,
            sequence_order=1,
        )

        self.prod_default = Product.objects.create(
            factory=self.factory,
            name="برطمان 500 مل",
            code="PRD-500",
            weight_per_piece_grams=25.0,
        )
        self.prod_alternative = Product.objects.create(
            factory=self.factory,
            name="غطاء برطمان",
            code="CAP-500",
            weight_per_piece_grams=5.0,
        )

        self.operator = MachineOperator.objects.create(
            factory=self.factory,
            name="علي حسن",
            phone="01011112222",
        )

        self.machine_default = MachineProductionDefault.objects.create(
            asset=self.asset1,
            default_product=self.prod_default,
            original_cavities=4,
            cooling_time_seconds=12.5,
            cycle_time_seconds=22.0,
            target_cycle_production=650.0,
        )

    def test_bootstrap_endpoint(self):
        self.client.force_authenticate(user=self.supervisor1)
        res = self.client.get("/api/v1/production/bootstrap/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(len(data["assets"]), 1)
        self.assertEqual(len(data["products"]), 2)
        self.assertEqual(len(data["operators"]), 1)
        # Check machine default populated
        asset_data = data["assets"][0]
        self.assertIsNotNone(asset_data["production_default"])
        self.assertEqual(asset_data["production_default"]["original_cavities"], 4)
        self.assertEqual(asset_data["production_default"]["cooling_time_seconds"], 12.5)

    def test_sync_shift_report_with_product_change(self):
        self.client.force_authenticate(user=self.supervisor1)
        client_id = str(uuid.uuid4())
        today = str(timezone.localdate())

        payload = {
            "client_report_id": client_id,
            "shift": "FIRST",
            "report_date": today,
            "status": "PENDING_HANDOVER",
            "general_notes": "وردية منتظمة",
            "entries": [
                {
                    "asset_id": self.asset1.id,
                    "operator_id": self.operator.id,
                    "operator_name": "علي حسن",
                    "product_id": self.prod_alternative.id, # Changed from PRD-500!
                    "product_name": "غطاء برطمان",
                    "original_cavities": 4,
                    "current_cavities": 3, # One cavity blocked
                    "operation_mode": "AUTO",
                    "cooling_time_seconds": 12.5,
                    "cycle_time_seconds": 22.0,
                    "raw_material": "PP سابك 500P",
                    "final_production_weight_kg": 450.5,
                    "target_cycle_production": 650.0,
                    "packaging_type": "شكاير",
                    "notes": "تم تعطيل لقمة واحدة لوجود رايش",
                }
            ],
            "stoppages": [
                {
                    "asset_id": None, # General
                    "stoppage_type": "FRIDAY_PRAYER",
                    "description": "صلاة الجمعة لجميع الماكينات",
                    "duration_minutes": 60,
                    "action_taken": "إيقاف جماعي مؤقت واستئناف بعد الصلاة",
                }
            ],
        }

        res = self.client.post("/api/v1/production/sync/shift-reports/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data["client_report_id"], client_id)
        self.assertEqual(data["status"], "PENDING_HANDOVER")
        self.assertEqual(len(data["machine_entries"]), 1)
        entry = data["machine_entries"][0]
        # Must detect product change!
        self.assertTrue(entry["product_changed"])
        self.assertEqual(entry["current_cavities"], 3)
        self.assertEqual(entry["original_cavities"], 4)


        # Stoppage
        self.assertEqual(len(data["stoppages"]), 1)
        self.assertEqual(data["stoppages"][0]["stoppage_type"], "FRIDAY_PRAYER")

        # Now test confirm handover by supervisor2
        self.client.force_authenticate(user=self.supervisor2)
        handover_res = self.client.post("/api/v1/production/reports/confirm-handover/", {
            "client_report_id": client_id,
            "handover_notes": "تم فحص الماكينات واستلام الوردية بالكامل بحالة جيدة",
        }, format="json")
        self.assertEqual(handover_res.status_code, status.HTTP_200_OK)
        handover_data = handover_res.json()
        self.assertEqual(handover_data["status"], "CONFIRMED")
        self.assertEqual(handover_data["handover_to_supervisor_name"], "م. محمود مستلم")

    def test_web_views_render(self):
        from django.test import Client
        web_client = Client()
        web_client.force_login(self.supervisor1)

        urls = [
            reverse("production:home"),
            reverse("production:reports"),
            reverse("production:machine_defaults"),
            reverse("production:products"),
            reverse("production:operators"),
            reverse("production:stoppages"),
        ]
        for url in urls:
            response = web_client.get(url)
            self.assertEqual(response.status_code, 200, f"URL {url} failed with {response.status_code}")

    def test_admin_can_access_without_factory(self):
        """Verify superuser / admin with factory=None has full access and never receives factory error."""
        admin_user = User.objects.create_superuser(
            phone="01099999999",
            password="adminpassword123",
            name="المدير العام",
        )
        self.assertIsNone(admin_user.factory)
        self.assertTrue(admin_user.is_admin)

        from django.test import Client
        admin_client = Client()
        admin_client.force_login(admin_user)

        # 1. Access production home
        response = admin_client.get(reverse("production:home"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "المستخدم غير مربوط بمصنع.")

        # 2. Access with factory switcher param
        response_all = admin_client.get(reverse("production:home") + "?factory=all")
        self.assertEqual(response_all.status_code, 200)
        self.assertNotContains(response_all, "المستخدم غير مربوط بمصنع.")

        response_f1 = admin_client.get(reverse("production:home") + f"?factory={self.factory.id}")
        self.assertEqual(response_f1.status_code, 200)

        # 3. Access other production views
        self.assertEqual(admin_client.get(reverse("production:reports")).status_code, 200)
        self.assertEqual(admin_client.get(reverse("production:machine_defaults")).status_code, 200)
        self.assertEqual(admin_client.get(reverse("production:products")).status_code, 200)
        self.assertEqual(admin_client.get(reverse("production:operators")).status_code, 200)
        self.assertEqual(admin_client.get(reverse("production:stoppages")).status_code, 200)

    def test_maintenance_supervisor_cannot_access_production(self):
        """User with only maintenance permissions is redirected from production."""
        maint_supervisor = User.objects.create_user(
            phone="01200000001",
            password="password123",
            name="مشرف صيانة فقط",
            role=User.Role.MAINTENANCE_SUPERVISOR,
            factory=self.factory,
        )
        self.assertTrue(maint_supervisor.can_access_maintenance)
        self.assertFalse(maint_supervisor.can_access_production)

        from django.test import Client
        client = Client()
        client.force_login(maint_supervisor)

        response = client.get(reverse("production:home"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard:home"))

    def test_factory_isolation_between_supervisors(self):
        """Supervisor in Factory 1 cannot see reports from Factory 2."""
        factory2, _ = Factory.objects.get_or_create(code="F2", defaults={"name": "مصنع الوسام 2"})
        supervisor_f2 = User.objects.create_user(
            phone="01200000002",
            password="password123",
            name="مشرف مصنع 2",
            role=User.Role.PRODUCTION_SUPERVISOR,
            factory=factory2,
        )

        # Create report in Factory 2
        report_f2 = ProductionShiftReport.objects.create(
            client_report_id=str(uuid.uuid4()),
            factory=factory2,
            supervisor=supervisor_f2,
            shift="FIRST",
            report_date=timezone.localdate(),
        )

        # Create report in Factory 1
        report_f1 = ProductionShiftReport.objects.create(
            client_report_id=str(uuid.uuid4()),
            factory=self.factory,
            supervisor=self.supervisor1,
            shift="FIRST",
            report_date=timezone.localdate(),
        )

        from django.test import Client
        client1 = Client()
        client1.force_login(self.supervisor1)

        # Supervisor 1 views reports
        res = client1.get(reverse("production:reports"))
        self.assertEqual(res.status_code, 200)
        reports_in_view = res.context["page_obj"].object_list
        self.assertIn(report_f1, reports_in_view)
        self.assertNotIn(report_f2, reports_in_view)

        # Supervisor 1 cannot access detail of report in Factory 2
        detail_res = client1.get(reverse("production:report_detail", args=[report_f2.id]))
        self.assertEqual(detail_res.status_code, 404)

    def test_report_detail_displays_changed_values_clearly(self):
        from django.test import Client
        report = ProductionShiftReport.objects.create(
            client_report_id=str(uuid.uuid4()),
            factory=self.factory,
            supervisor=self.supervisor1,
            shift="FIRST",
            report_date=timezone.localdate(),
        )
        MachineProductionEntry.objects.create(
            report=report,
            asset=self.asset1,
            operator_name="أحمد محمود",
            original_operator_name="محمد علي",
            operator_changed=True,
            product_name="جركن 20 لتر جديد",
            original_product_name="جركن 10 لتر قديم",
            product_changed=True,
            final_production_weight_kg=150.0,
        )

        client = Client()
        client.force_login(self.supervisor1)

        # 1. Check report detail page displays explicit change text
        res = client.get(reverse("production:report_detail", args=[report.id]))
        self.assertEqual(res.status_code, 200)
        content = res.content.decode("utf-8")
        self.assertIn("تم تغيير العامل!", content)
        self.assertIn("كانت القيمة:", content)
        self.assertIn("محمد علي", content)
        self.assertIn("أحمد محمود", content)
        self.assertIn("تم تغيير المنتج!", content)
        self.assertIn("جركن 10 لتر قديم", content)
        self.assertIn("جركن 20 لتر جديد", content)
        self.assertIn("وتم تغييرها إلى:", content)

        # 2. Check home dashboard reflects changes in stats and recent reports
        home_res = client.get(reverse("production:home"))
        self.assertEqual(home_res.status_code, 200)
        home_content = home_res.content.decode("utf-8")
        self.assertIn("تغييرات العمال والمنتجات اليوم", home_content)
        self.assertIn("تغيير منتج", home_content)
        self.assertIn("تغيير عامل", home_content)

    def test_machine_defaults_view_and_edit_use_asset_code(self):
        from django.test import Client
        client = Client()
        client.force_login(self.supervisor1)

        # 1. Machine defaults list renders asset_code and does not have machine name column
        res = client.get(reverse("production:machine_defaults"))
        self.assertEqual(res.status_code, 200)
        content = res.content.decode("utf-8")
        self.assertIn("M-01", content)
        self.assertNotIn("اسم الماكينة", content)

        # 2. Machine default edit page renders asset_code
        edit_url = reverse("production:machine_default_edit", args=[self.asset1.id])
        edit_res = client.get(edit_url)
        self.assertEqual(edit_res.status_code, 200)
        edit_content = edit_res.content.decode("utf-8")
        self.assertIn("M-01", edit_content)

        # 3. Post edit form and check redirect and success message with asset_code
        post_res = client.post(edit_url, {
            "default_product": self.prod_default.id,
            "default_operator": self.operator.id,
            "original_cavities": 4,
            "cooling_time_seconds": 12.5,
            "cycle_time_seconds": 25.0,
            "target_cycle_production": 400.0,
        }, follow=True)
        self.assertEqual(post_res.status_code, 200)
        post_content = post_res.content.decode("utf-8")
        self.assertIn("تم تحديث إعدادات الإنتاج لماكينة M-01 بنجاح.", post_content)
        self.assertIn("M-01", post_content)

    def test_three_shifts_automatic_handover_logic(self):
        # 1. Create 3 supervisors assigned to the 3 shifts in factory 1
        sup1 = User.objects.create_user(
            phone="01011111111",
            password="pass",
            name="مشرف وردية 1",
            role=User.Role.PRODUCTION_SUPERVISOR,
            factory=self.factory,
            shift=User.Shift.FIRST
        )
        sup2 = User.objects.create_user(
            phone="01022222222",
            password="pass",
            name="مشرف وردية 2",
            role=User.Role.PRODUCTION_SUPERVISOR,
            factory=self.factory,
            shift=User.Shift.SECOND
        )
        sup3 = User.objects.create_user(
            phone="01033333333",
            password="pass",
            name="مشرف وردية 3",
            role=User.Role.PRODUCTION_SUPERVISOR,
            factory=self.factory,
            shift=User.Shift.THIRD
        )

        # Check cyclic next/previous shifts
        self.assertEqual(sup1.next_shift, "SECOND")
        self.assertEqual(sup1.get_next_shift_supervisor(), sup2)
        self.assertEqual(sup2.next_shift, "THIRD")
        self.assertEqual(sup2.get_next_shift_supervisor(), sup3)
        self.assertEqual(sup3.next_shift, "FIRST")
        self.assertEqual(sup3.get_next_shift_supervisor(), sup1)

        self.assertEqual(sup1.previous_shift, "THIRD")
        self.assertEqual(sup2.previous_shift, "FIRST")
        self.assertEqual(sup3.previous_shift, "SECOND")

        # 2. Supervisor 1 finishes FIRST shift report
        client_rep_id = str(uuid.uuid4())
        today_str = str(timezone.localdate())

        self.client.force_authenticate(user=sup1)
        sync_payload = {
            "client_report_id": client_rep_id,
            "shift": "FIRST",
            "report_date": today_str,
            "status": "PENDING_HANDOVER",
            "general_notes": "تم تسليم الوردية 1 بنجاح",
            "entries": [
                {
                    "asset_id": self.asset1.id,
                    "product_id": self.prod_default.id,
                    "original_cavities": 4,
                    "current_cavities": 4,
                    "final_production_weight_kg": 250.0,
                }
            ],
            "stoppages": []
        }
        res_sync = self.client.post(reverse("production-api:sync-shift-reports"), sync_payload, format="json")
        self.assertEqual(res_sync.status_code, 200)

        # Check report in DB: handover_to_supervisor should be automatically sup2!
        rep = ProductionShiftReport.objects.get(client_report_id=client_rep_id)
        self.assertEqual(rep.supervisor, sup1)
        self.assertEqual(rep.handover_to_supervisor, sup2)
        self.assertEqual(rep.status, ProductionShiftReport.Status.PENDING_HANDOVER)

        # 3. Supervisor 2 logs in / opens app -> calls Bootstrap
        self.client.force_authenticate(user=sup2)
        res_bootstrap = self.client.get(reverse("production-api:bootstrap"))
        self.assertEqual(res_bootstrap.status_code, 200)
        data = res_bootstrap.data

        # Bootstrap user info has shift and next supervisor (sup3)
        self.assertEqual(data["user"]["shift"], "SECOND")
        self.assertEqual(data["user"]["next_shift"], "THIRD")
        self.assertEqual(data["user"]["next_shift_supervisor"]["id"], sup3.id)
        self.assertEqual(data["user"]["next_shift_supervisor"]["name"], "مشرف وردية 3")

        # Pending handover is automatically sup1's report!
        self.assertIsNotNone(data["pending_handover"])
        self.assertEqual(data["pending_handover"]["client_report_id"], client_rep_id)
        self.assertEqual(data["pending_handover"]["shift"], "FIRST")

        # 4. Supervisor 2 confirms handover
        res_confirm = self.client.post(
            reverse("production-api:confirm-handover"),
            {"client_report_id": client_rep_id, "handover_notes": "تم استلام جميع الماكينات بحالة جيدة"},
            format="json"
        )
        self.assertEqual(res_confirm.status_code, 200)

        rep.refresh_from_db()
        self.assertEqual(rep.status, ProductionShiftReport.Status.CONFIRMED)
        self.assertEqual(rep.handover_to_supervisor, sup2)
        self.assertIsNotNone(rep.handover_confirmed_at)
        self.assertEqual(rep.handover_notes, "تم استلام جميع الماكينات بحالة جيدة")

        # Calling bootstrap again for sup2 shows no pending handover
        res_bootstrap2 = self.client.get(reverse("production-api:bootstrap"))
        self.assertIsNone(res_bootstrap2.data["pending_handover"])

    def test_empty_sync_never_wipes_recorded_machine_entries(self):
        client_rep_id = str(uuid.uuid4())
        today_str = str(timezone.localdate())

        self.client.force_authenticate(user=self.supervisor1)
        
        # 1. First sync sends 1 recorded machine entry
        initial_sync = {
            "client_report_id": client_rep_id,
            "shift": "FIRST",
            "report_date": today_str,
            "status": "PENDING_HANDOVER",
            "general_notes": "تسجيل ماكينة تجريبية",
            "entries": [
                {
                    "asset_id": self.asset1.id,
                    "product_id": self.prod_default.id,
                    "original_cavities": 4,
                    "current_cavities": 4,
                    "final_production_weight_kg": 320.5,
                }
            ],
            "stoppages": []
        }
        res1 = self.client.post(reverse("production-api:sync-shift-reports"), initial_sync, format="json")
        self.assertEqual(res1.status_code, 200)

        rep = ProductionShiftReport.objects.get(client_report_id=client_rep_id)
        self.assertEqual(rep.machine_entries.count(), 1)
        entry = rep.machine_entries.first()
        self.assertEqual(entry.asset, self.asset1)
        self.assertEqual(entry.final_production_weight_kg, 320.5)

        # 2. Subsequent sync sent with empty entries list (e.g. status update or finish shift without entries)
        finish_sync = {
            "client_report_id": client_rep_id,
            "shift": "FIRST",
            "report_date": today_str,
            "status": "PENDING_HANDOVER",
            "general_notes": "تم إنهاء الوردية",
            "entries": [],
            "stoppages": []
        }
        res2 = self.client.post(reverse("production-api:sync-shift-reports"), finish_sync, format="json")
        self.assertEqual(res2.status_code, 200)

        # Machine entries MUST NOT be wiped!
        rep.refresh_from_db()
        self.assertEqual(rep.machine_entries.count(), 1, "Recorded machine entries must be preserved when sync entries is empty")
        self.assertEqual(rep.general_notes, "تم إنهاء الوردية")





