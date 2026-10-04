from django.contrib import admin
from .models import (
    Product,
    MachineOperator,
    ProductionOption,
    MachineProductionDefault,
    ProductionShiftReport,
    MachineProductionEntry,
    ProductionStoppage,
)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "factory", "weight_per_piece_grams", "is_active"]
    list_filter = ["factory", "is_active"]
    search_fields = ["name", "code"]

@admin.register(MachineOperator)
class MachineOperatorAdmin(admin.ModelAdmin):
    list_display = ["name", "factory", "phone", "is_active"]
    list_filter = ["factory", "is_active"]
    search_fields = ["name", "phone"]

@admin.register(MachineProductionDefault)
class MachineProductionDefaultAdmin(admin.ModelAdmin):
    list_display = ["asset", "default_product", "default_operator", "default_raw_material", "default_final_unit", "original_cavities", "cooling_time_seconds", "cycle_time_seconds", "target_cycle_production", "target_cycle_unit", "default_packaging"]
    list_filter = ["asset__factory"]
    search_fields = ["asset__asset_code"]

class MachineProductionEntryInline(admin.TabularInline):
    model = MachineProductionEntry
    extra = 0
    fields = ["asset", "operator_name", "operator_changed", "original_operator_name", "product_name", "product_changed", "original_product_name", "current_cavities", "operation_mode", "raw_material", "final_production_weight_kg", "packaging_type"]

class ProductionStoppageInline(admin.TabularInline):
    model = ProductionStoppage
    extra = 0
    fields = ["asset", "stoppage_type", "description", "duration_minutes", "action_taken"]

@admin.register(ProductionShiftReport)
class ProductionShiftReportAdmin(admin.ModelAdmin):
    list_display = ["report_date", "factory", "shift", "supervisor", "status", "handover_to_supervisor", "handover_confirmed_at"]
    list_filter = ["factory", "shift", "status", "report_date"]
    search_fields = ["supervisor__name", "supervisor__phone"]
    inlines = [MachineProductionEntryInline, ProductionStoppageInline]

@admin.register(ProductionStoppage)
class ProductionStoppageAdmin(admin.ModelAdmin):
    list_display = ["report", "asset", "stoppage_type", "duration_minutes", "created_at"]
    list_filter = ["stoppage_type", "report__factory"]
    search_fields = ["description", "action_taken"]


@admin.register(ProductionOption)
class ProductionOptionAdmin(admin.ModelAdmin):
    list_display = ["name", "factory", "category", "kg_per_unit", "is_active"]
    list_filter = ["factory", "category", "is_active"]
    search_fields = ["name"]
