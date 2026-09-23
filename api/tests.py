import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from accounts.models import User
from assets.models import Asset
from factories.models import Factory
from maintenance.models import ChecklistItem
from maintenance.services.cycle import MaintenanceCycleService

class ApiSecurityTests(TestCase):
    def setUp(self):
        self.f1=Factory.objects.get(code="F1"); self.f2=Factory.objects.get(code="F2"); self.asset=Asset.objects.create(factory=self.f1,asset_type=Asset.Type.REGULAR_MACHINE,asset_code="API-ONLY",sequence_order=1); self.other=Asset.objects.create(factory=self.f2,asset_type=Asset.Type.REGULAR_MACHINE,asset_code="OTHER",sequence_order=1)
        self.user=User.objects.create_user("01111111111","StrongPass!123",factory=self.f1); self.admin=User.objects.create_user("01333333333","StrongPass!123",role=User.Role.ADMIN); self.client=APIClient()
    def auth(self,user=None): self.client.force_authenticate(user or self.user)
    def payload(self,asset=None,date=None):
        asset=asset or self.asset; date=date or timezone.localdate(); start=datetime.combine(date,datetime.min.time(),tzinfo=ZoneInfo("Africa/Cairo"))+timedelta(hours=8); template=MaintenanceCycleService.template_for(asset)
        return {"client_report_id":str(uuid.uuid4()),"asset_id":asset.id,"report_date":str(date),"started_at_device":start.isoformat(),"completed_at_device":(start+timedelta(minutes=10)).isoformat(),"last_modified_at_device":(start+timedelta(minutes=10)).isoformat(),"answers":[{"checklist_item_id":i.id,"checked":False,"note":""} for s in template.sections.all() for i in s.items.all()]}
    def test_login_and_bootstrap_scoped_to_factory(self):
        response=self.client.post("/api/v1/auth/login/",{"phone":self.user.phone,"password":"StrongPass!123"},format="json"); self.assertEqual(response.status_code,200); self.assertIn("access",response.data); self.auth(); boot=self.client.get("/api/v1/mobile/bootstrap/"); self.assertEqual(boot.status_code,200); self.assertEqual(boot.data["factory"]["id"],self.f1.id); self.assertEqual([a["id"] for a in boot.data["active_assets"]],[self.asset.id])
    def test_bootstrap_excludes_inactive_items_and_sync_accepts_its_checklist(self):
        template = MaintenanceCycleService.template_for(self.asset)
        section = template.sections.first()
        inactive = ChecklistItem.objects.create(section=section, text="inactive", sequence_order=999, is_active=False)
        self.auth()
        boot = self.client.get("/api/v1/mobile/bootstrap/")
        self.assertEqual(boot.status_code, 200)
        item_ids = {
            item["id"]
            for template_data in boot.data["checklist_templates"]
            for section_data in template_data["sections"]
            for item in section_data["items"]
        }
        self.assertNotIn(inactive.id, item_ids)
        response = self.client.post("/api/v1/mobile/sync/reports/", {"reports": [self.payload()]}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["status"], "synced")
    def test_supervisor_cannot_report_other_factory_asset(self): self.auth(); self.assertEqual(self.client.post("/api/v1/mobile/reports/",self.payload(self.other),format="json").status_code,400)
    def test_report_create_and_same_day_update(self):
        self.auth(); payload=self.payload(); created=self.client.post("/api/v1/mobile/reports/",payload,format="json"); self.assertEqual(created.status_code,201); payload["answers"][0]["checked"]=True; payload["last_modified_at_device"]=(datetime.fromisoformat(payload["last_modified_at_device"])+timedelta(minutes=1)).isoformat(); updated=self.client.put(f"/api/v1/mobile/reports/{created.data['report']['id']}/",payload,format="json"); self.assertEqual(updated.status_code,201); self.assertTrue(updated.data["report"]["answers"][0]["checked"])
    def test_batch_duplicate_does_not_abort_results(self): self.auth(); payload=self.payload(); response=self.client.post("/api/v1/mobile/sync/reports/",{"reports":[payload,payload]},format="json"); self.assertEqual(response.status_code,200); self.assertEqual(len(response.data["results"]),2)
    def test_admin_cannot_use_mobile_endpoint(self): self.auth(self.admin); self.assertEqual(self.client.get("/api/v1/mobile/bootstrap/").status_code,403)
    def test_supervisor_can_select_active_asset_in_own_factory(self):
        second=Asset.objects.create(factory=self.f1,asset_type=Asset.Type.REGULAR_MACHINE,asset_code="SECOND",sequence_order=2); self.auth()
        response=self.client.post("/api/v1/mobile/current-maintenance/select/",{"asset_id":second.id},format="json")
        self.assertEqual(response.status_code,200); self.assertEqual(response.data["asset"]["id"],second.id); self.assertEqual(response.data["selection_mode"],"manual")
    def test_supervisor_cannot_select_other_factory_asset(self):
        self.auth(); response=self.client.post("/api/v1/mobile/current-maintenance/select/",{"asset_id":self.other.id},format="json"); self.assertEqual(response.status_code,400)
    def test_dashboard_is_admin_only(self):
        self.client.force_authenticate(user=None); self.client.login(phone=self.user.phone,password="StrongPass!123"); self.assertEqual(self.client.get("/").status_code,302); self.client.logout(); self.client.login(phone=self.admin.phone,password="StrongPass!123"); self.assertEqual(self.client.get("/").status_code,200)
