from django.contrib import admin
from assets.models import Asset
@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ["asset_code", "factory", "asset_type", "sequence_order", "is_active", "is_archived"]; list_filter = ["factory", "asset_type", "is_active", "is_archived"]; search_fields = ["asset_code"]
