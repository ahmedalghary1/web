import os
import django
import json
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from accounts.models import User
from factories.models import Factory
from assets.models import Asset
from maintenance.models import ChecklistTemplate, ChecklistSection, ChecklistItem
from api.views import current_payload
from api.serializers import UserSerializer, AssetSerializer, ChecklistTemplateSerializer
from maintenance.services.cycle import MaintenanceCycleService

f, _ = Factory.objects.get_or_create(name="F1", code="F1")
u, _ = User.objects.get_or_create(phone="010", defaults={"role": "MAINTENANCE_SUPERVISOR", "factory": f})
Asset.objects.get_or_create(factory=f, asset_type="REGULAR_MACHINE", asset_code="MAC-01")
t, _ = ChecklistTemplate.objects.get_or_create(name="Temp 1", code="STANDARD", is_active=True)
s, _ = ChecklistSection.objects.get_or_create(template=t, name="Sec 1")
ChecklistItem.objects.get_or_create(section=s, text="Item 1")

payload = current_payload(u)
payload.update(
    user=UserSerializer(u).data,
    active_assets=AssetSerializer(MaintenanceCycleService.active_assets(u.factory), many=True).data,
    checklist_templates=ChecklistTemplateSerializer(
        ChecklistTemplate.objects.filter(is_active=True).prefetch_related("sections__items"), many=True
    ).data
)
print(json.dumps(payload, default=str, ensure_ascii=False, indent=2))
