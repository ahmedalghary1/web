from rest_framework import serializers
from assets.models import Asset
from factories.models import Factory
from accounts.models import User
from .models import (
    Product,
    MachineOperator,
    MachineProductionDefault,
    ProductionShiftReport,
    MachineProductionEntry,
    ProductionStoppage,
)

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ["id", "name", "code", "weight_per_piece_grams", "is_active"]

class MachineOperatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = MachineOperator
        fields = ["id", "name", "phone", "is_active"]

class MachineProductionDefaultSerializer(serializers.ModelSerializer):
    default_product_name = serializers.CharField(source="default_product.name", read_only=True, default="")
    default_operator_name = serializers.CharField(source="default_operator.name", read_only=True, default="")
    class Meta:
        model = MachineProductionDefault
        fields = [
            "default_product",
            "default_product_name",
            "default_operator",
            "default_operator_name",
            "original_cavities",
            "cooling_time_seconds",
            "cycle_time_seconds",
            "target_cycle_production",
        ]

class ProductionAssetSerializer(serializers.ModelSerializer):
    asset_type_display = serializers.CharField(source="get_asset_type_display", read_only=True)
    production_title = serializers.CharField(read_only=True)
    maintenance_title = serializers.CharField(source="production_title", read_only=True)
    production_default = MachineProductionDefaultSerializer(read_only=True)

    class Meta:
        model = Asset
        fields = [
            "id",
            "asset_code",
            "asset_type",
            "asset_type_display",
            "sequence_order",
            "is_active",
            "production_title",
            "maintenance_title",
            "production_default",
        ]

class MachineProductionEntrySerializer(serializers.ModelSerializer):
    asset_code = serializers.CharField(source="asset.asset_code", read_only=True)
    production_title = serializers.CharField(source="asset.production_title", read_only=True)
    maintenance_title = serializers.CharField(source="asset.production_title", read_only=True)
    
    class Meta:
        model = MachineProductionEntry
        fields = [
            "id",
            "asset",
            "asset_code",
            "production_title",
            "maintenance_title",
            "operator",
            "operator_name",
            "original_operator",
            "original_operator_name",
            "operator_changed",
            "product",
            "product_name",
            "original_product",
            "original_product_name",
            "product_changed",
            "original_cavities",
            "current_cavities",
            "operation_mode",
            "cooling_time_seconds",
            "cycle_time_seconds",
            "raw_material",
            "final_production_weight_kg",
            "target_cycle_production",
            "packaging_type",
            "notes",
        ]

class ProductionStoppageSerializer(serializers.ModelSerializer):
    asset_code = serializers.CharField(source="asset.asset_code", read_only=True, default="")
    stoppage_type_display = serializers.CharField(source="get_stoppage_type_display", read_only=True)

    class Meta:
        model = ProductionStoppage
        fields = [
            "id",
            "asset",
            "asset_code",
            "stoppage_type",
            "stoppage_type_display",
            "description",
            "duration_minutes",
            "action_taken",
            "created_at",
        ]

class ProductionShiftReportSerializer(serializers.ModelSerializer):
    supervisor_name = serializers.CharField(source="supervisor.display_name", read_only=True)
    shift_display = serializers.CharField(source="get_shift_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    handover_to_supervisor_name = serializers.CharField(source="handover_to_supervisor.display_name", read_only=True, default="")
    machine_entries = MachineProductionEntrySerializer(many=True, read_only=True)
    stoppages = ProductionStoppageSerializer(many=True, read_only=True)

    class Meta:
        model = ProductionShiftReport
        fields = [
            "id",
            "client_report_id",
            "factory",
            "supervisor",
            "supervisor_name",
            "shift",
            "shift_display",
            "report_date",
            "started_at_device",
            "completed_at_device",
            "status",
            "status_display",
            "handover_to_supervisor",
            "handover_to_supervisor_name",
            "handover_confirmed_at",
            "handover_notes",
            "general_notes",
            "total_production_weight_kg",
            "changed_products_count",
            "changed_operators_count",
            "machine_entries",
            "stoppages",
            "created_at",
        ]

# Payload Serializer for incoming sync from mobile app
class SyncMachineEntryInputSerializer(serializers.Serializer):
    asset_id = serializers.IntegerField()
    operator_id = serializers.IntegerField(required=False, allow_null=True)
    operator_name = serializers.CharField(required=False, allow_blank=True, default="")
    original_operator_id = serializers.IntegerField(required=False, allow_null=True)
    original_operator_name = serializers.CharField(required=False, allow_blank=True, default="")
    operator_changed = serializers.BooleanField(default=False)
    product_id = serializers.IntegerField(required=False, allow_null=True)
    product_name = serializers.CharField(required=False, allow_blank=True, default="")
    original_product_id = serializers.IntegerField(required=False, allow_null=True)
    original_product_name = serializers.CharField(required=False, allow_blank=True, default="")
    product_changed = serializers.BooleanField(default=False)
    original_cavities = serializers.IntegerField(default=1)
    current_cavities = serializers.IntegerField(default=1)
    operation_mode = serializers.ChoiceField(choices=["AUTO", "MANUAL"], default="AUTO")
    cooling_time_seconds = serializers.FloatField(default=0.0)
    cycle_time_seconds = serializers.FloatField(default=0.0)
    raw_material = serializers.CharField(required=False, allow_blank=True, default="")
    final_production_weight_kg = serializers.FloatField(default=0.0)
    target_cycle_production = serializers.FloatField(default=0.0)
    packaging_type = serializers.CharField(required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")

class SyncStoppageInputSerializer(serializers.Serializer):
    asset_id = serializers.IntegerField(required=False, allow_null=True)
    stoppage_type = serializers.CharField(default="MACHINE_BREAKDOWN")
    description = serializers.CharField()
    duration_minutes = serializers.IntegerField(default=0)
    action_taken = serializers.CharField(required=False, allow_blank=True, default="")

class SyncShiftReportInputSerializer(serializers.Serializer):
    client_report_id = serializers.UUIDField()
    shift = serializers.ChoiceField(choices=["FIRST", "SECOND", "THIRD"], default="FIRST")
    report_date = serializers.DateField()
    started_at_device = serializers.DateTimeField(required=False, allow_null=True)
    completed_at_device = serializers.DateTimeField(required=False, allow_null=True)
    status = serializers.ChoiceField(choices=["DRAFT", "PENDING_HANDOVER", "CONFIRMED"], default="PENDING_HANDOVER")
    general_notes = serializers.CharField(required=False, allow_blank=True, default="")
    entries = SyncMachineEntryInputSerializer(many=True, required=False, default=[])
    stoppages = SyncStoppageInputSerializer(many=True, required=False, default=[])

class ConfirmHandoverInputSerializer(serializers.Serializer):
    client_report_id = serializers.UUIDField()
    handover_notes = serializers.CharField(required=False, allow_blank=True, default="")
