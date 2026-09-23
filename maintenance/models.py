import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

class ChecklistTemplate(models.Model):
    code = models.CharField(max_length=40, unique=True); name = models.CharField(max_length=120); version = models.PositiveIntegerField(default=1); is_active = models.BooleanField(default=True)
    def __str__(self): return self.name
class ChecklistSection(models.Model):
    template = models.ForeignKey(ChecklistTemplate, on_delete=models.PROTECT, related_name="sections"); name = models.CharField(max_length=150); sequence_order = models.PositiveIntegerField()
    class Meta: ordering = ["sequence_order"]; constraints = [models.UniqueConstraint(fields=["template", "sequence_order"], name="uniq_section_order")]
class ChecklistItem(models.Model):
    section = models.ForeignKey(ChecklistSection, on_delete=models.PROTECT, related_name="items"); text = models.CharField(max_length=300); sequence_order = models.PositiveIntegerField(); is_active = models.BooleanField(default=True)
    class Meta: ordering = ["sequence_order"]; constraints = [models.UniqueConstraint(fields=["section", "sequence_order"], name="uniq_item_order")]
class FactoryMaintenanceState(models.Model):
    factory = models.OneToOneField("factories.Factory", on_delete=models.CASCADE, related_name="maintenance_state"); current_asset = models.ForeignKey("assets.Asset", null=True, blank=True, on_delete=models.SET_NULL, related_name="current_for_states"); current_effective_date = models.DateField(null=True, blank=True); last_completed_asset = models.ForeignKey("assets.Asset", null=True, blank=True, on_delete=models.SET_NULL, related_name="completed_for_states"); last_completed_date = models.DateField(null=True, blank=True, db_index=True); order_version = models.PositiveIntegerField(default=1); manual_selected_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="manual_maintenance_selections"); manual_selected_at = models.DateTimeField(null=True, blank=True); updated_at = models.DateTimeField(auto_now=True)
class MaintenanceReport(models.Model):
    client_report_id = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True); factory = models.ForeignKey("factories.Factory", on_delete=models.PROTECT, related_name="reports"); asset = models.ForeignKey("assets.Asset", on_delete=models.PROTECT, related_name="reports"); supervisor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="maintenance_reports")
    report_date = models.DateField(db_index=True); started_at_device = models.DateTimeField(); completed_at_device = models.DateTimeField(); last_modified_at_device = models.DateTimeField(); created_at = models.DateTimeField(auto_now_add=True); updated_at = models.DateTimeField(auto_now=True); completed_at = models.DateTimeField(default=timezone.now); is_locked = models.BooleanField(default=False, db_index=True)
    cleaner_name = models.CharField(max_length=150, blank=True, default="", verbose_name="القائم بالنظافة")
    mechanical_technician = models.CharField(max_length=150, blank=True, default="", verbose_name="القائم بالصيانة الميكانيكية")
    electrical_technician = models.CharField(max_length=150, blank=True, default="", verbose_name="القائم بالصيانة الكهربية")
    maintenance_manager = models.CharField(max_length=150, blank=True, default="", verbose_name="مدير الصيانة")
    class Meta:
        ordering = ["-report_date", "-created_at"]
        constraints = [models.UniqueConstraint(fields=["factory", "report_date"], name="uniq_factory_report_date"), models.CheckConstraint(condition=Q(completed_at_device__gte=models.F("started_at_device")), name="report_device_times_ordered")]
        indexes = [models.Index(fields=["factory", "report_date"]), models.Index(fields=["asset", "report_date"]), models.Index(fields=["supervisor", "report_date"])]
    @property
    def effectively_locked(self): return self.is_locked or self.report_date < timezone.localdate()
    @property
    def title(self): return self.asset.maintenance_title
    def __str__(self): return f"{self.asset.maintenance_title} ({self.report_date})"
class MaintenanceReportItem(models.Model):
    report = models.ForeignKey(MaintenanceReport, on_delete=models.CASCADE, related_name="answers"); checklist_item = models.ForeignKey(ChecklistItem, on_delete=models.PROTECT, related_name="report_answers"); checked = models.BooleanField(default=False); note = models.TextField(blank=True)
    class Meta: constraints = [models.UniqueConstraint(fields=["report", "checklist_item"], name="uniq_report_item")]

class EmergencyMaintenanceItem(models.Model):
    report = models.ForeignKey(MaintenanceReport, on_delete=models.CASCADE, related_name="emergency_items")
    asset = models.ForeignKey("assets.Asset", on_delete=models.PROTECT, related_name="emergency_maintenances")
    issue_description = models.TextField(verbose_name="العطل")
    responsible_person = models.CharField(max_length=150, verbose_name="المسؤول")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "بند صيانة طارئة"
        verbose_name_plural = "بنود الصيانة الطارئة"

    def __str__(self):
        return f"{self.asset.asset_code} - {self.issue_description[:30]}"
