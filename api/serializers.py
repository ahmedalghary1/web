from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from accounts.models import User
from assets.models import Asset
from factories.models import Factory
from maintenance.models import ChecklistTemplate, MaintenanceReport, MaintenanceReportItem, EmergencyMaintenanceItem

class FactorySerializer(serializers.ModelSerializer):
    class Meta: model = Factory; fields = ["id", "name", "code"]
class UserSerializer(serializers.ModelSerializer):
    factory = FactorySerializer(read_only=True)
    display_name = serializers.CharField(read_only=True)
    shift_display = serializers.CharField(source="get_shift_display", read_only=True)
    class Meta: model = User; fields = ["id", "name", "phone", "display_name", "role", "factory", "shift", "shift_display"]
class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs); data["user"] = UserSerializer(self.user).data; return data
class AssetSerializer(serializers.ModelSerializer):
    asset_type_display = serializers.CharField(source="get_asset_type_display", read_only=True)
    class Meta: model = Asset; fields = ["id", "asset_code", "asset_type", "asset_type_display", "sequence_order", "is_active"]
class ChecklistItemSerializer(serializers.Serializer):
    id = serializers.IntegerField(); text = serializers.CharField(); sequence_order = serializers.IntegerField()
class ChecklistSectionSerializer(serializers.Serializer):
    id = serializers.IntegerField(); name = serializers.CharField(); sequence_order = serializers.IntegerField(); items = ChecklistItemSerializer(many=True)
class ChecklistTemplateSerializer(serializers.ModelSerializer):
    sections = ChecklistSectionSerializer(many=True)
    class Meta: model = ChecklistTemplate; fields = ["id", "code", "name", "version", "sections"]
class ReportItemSerializer(serializers.ModelSerializer):
    checklist_item_id = serializers.IntegerField()
    text = serializers.CharField(source="checklist_item.text", read_only=True)
    class Meta: model = MaintenanceReportItem; fields = ["checklist_item_id", "text", "checked", "note"]
class EmergencyItemSerializer(serializers.ModelSerializer):
    asset = AssetSerializer(read_only=True)
    asset_id = serializers.IntegerField(source="asset.id", read_only=True)
    class Meta: model = EmergencyMaintenanceItem; fields = ["id", "asset", "asset_id", "issue_description", "responsible_person", "notes"]
class ReportSerializer(serializers.ModelSerializer):
    answers = ReportItemSerializer(many=True, read_only=True)
    emergency_items = EmergencyItemSerializer(many=True, read_only=True)
    asset = AssetSerializer(read_only=True)
    is_locked = serializers.SerializerMethodField()
    class Meta:
        model = MaintenanceReport
        fields = [
            "id", "client_report_id", "factory_id", "asset", "supervisor_id",
            "report_date", "started_at_device", "completed_at_device", "last_modified_at_device",
            "cleaner_name", "mechanical_technician", "electrical_technician", "maintenance_manager",
            "created_at", "updated_at", "completed_at", "is_locked", "answers", "emergency_items"
        ]
    def get_is_locked(self, obj): return obj.effectively_locked
class AnswerInputSerializer(serializers.Serializer):
    checklist_item_id = serializers.IntegerField(min_value=1); checked = serializers.BooleanField(); note = serializers.CharField(required=False, allow_blank=True, default="")
class EmergencyItemInputSerializer(serializers.Serializer):
    asset_id = serializers.IntegerField(min_value=1); issue_description = serializers.CharField(max_length=500, allow_blank=False); responsible_person = serializers.CharField(max_length=150, allow_blank=False); notes = serializers.CharField(required=False, allow_blank=True, default="")
class ReportInputSerializer(serializers.Serializer):
    client_report_id = serializers.UUIDField()
    asset_id = serializers.IntegerField(min_value=1)
    report_date = serializers.DateField()
    started_at_device = serializers.DateTimeField()
    completed_at_device = serializers.DateTimeField()
    last_modified_at_device = serializers.DateTimeField()
    cleaner_name = serializers.CharField(required=False, allow_blank=True, default="")
    mechanical_technician = serializers.CharField(required=False, allow_blank=True, default="")
    electrical_technician = serializers.CharField(required=False, allow_blank=True, default="")
    maintenance_manager = serializers.CharField(required=False, allow_blank=True, default="")
    answers = AnswerInputSerializer(many=True, allow_empty=False)
    emergency_items = EmergencyItemInputSerializer(many=True, required=False, default=list)

class CurrentAssetSelectionSerializer(serializers.Serializer):
    asset_id = serializers.IntegerField(min_value=1)

class BatchSyncSerializer(serializers.Serializer):
    reports = ReportInputSerializer(many=True, allow_empty=False)
    def validate_reports(self, value):
        return sorted(value, key=lambda x: (x["report_date"], x["completed_at_device"]))
