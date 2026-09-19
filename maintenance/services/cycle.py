import logging
from dataclasses import dataclass
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone
from rest_framework.exceptions import ValidationError, PermissionDenied
from assets.models import Asset
from maintenance.models import ChecklistItem, ChecklistTemplate, FactoryMaintenanceState, MaintenanceReport, MaintenanceReportItem

logger = logging.getLogger("maintenance")

@dataclass
class SyncResult:
    status: str
    report: MaintenanceReport | None = None
    reason: str = ""

class MaintenanceCycleService:
    TEMPLATE_BY_TYPE = {Asset.Type.REGULAR_MACHINE: "STANDARD", Asset.Type.PRESS: "STANDARD", Asset.Type.SPRING_MACHINE: "SPRING"}

    @staticmethod
    def is_maintenance_day(target_date):
        """Friday is the weekly maintenance holiday (Monday is zero)."""
        return target_date.weekday() != 4

    @classmethod
    def _type_rank(cls, factory):
        second = Asset.Type.SPRING_MACHINE if factory.code == "F2" else Asset.Type.PRESS
        return {Asset.Type.REGULAR_MACHINE: 0, second: 1}

    @classmethod
    def active_assets(cls, factory):
        rank = cls._type_rank(factory)
        return sorted(Asset.objects.filter(factory=factory, is_active=True, is_archived=False), key=lambda a: (rank.get(a.asset_type, 99), a.sequence_order, a.id))

    @classmethod
    def template_for(cls, asset):
        active_items = Prefetch("sections__items", queryset=ChecklistItem.objects.filter(is_active=True))
        return ChecklistTemplate.objects.prefetch_related(active_items).get(code=cls.TEMPLATE_BY_TYPE[asset.asset_type], is_active=True)

    @classmethod
    def _next_after(cls, factory, previous):
        assets = cls.active_assets(factory)
        if not assets: return None
        ids = [a.id for a in assets]
        if previous and previous.id in ids: return assets[(ids.index(previous.id) + 1) % len(assets)]
        if previous:
            rank = cls._type_rank(factory); old_key = (rank.get(previous.asset_type, 99), previous.sequence_order, previous.id)
            return next((a for a in assets if (rank.get(a.asset_type, 99), a.sequence_order, a.id) > old_key), assets[0])
        return assets[0]

    @classmethod
    @transaction.atomic
    def current_asset(cls, factory, target_date=None, lock=False):
        target_date = target_date or timezone.localdate()
        qs = FactoryMaintenanceState.objects.select_related("current_asset", "last_completed_asset")
        if lock: qs = qs.select_for_update()
        state, _ = qs.get_or_create(factory=factory)
        if not cls.is_maintenance_day(target_date):
            return None, state
        active_ids = {a.id for a in cls.active_assets(factory)}
        if state.current_effective_date == target_date and state.current_asset_id in active_ids:
            desired = state.current_asset
        elif (
            state.current_asset_id in active_ids
            and state.current_effective_date
            and (not state.last_completed_date or state.current_effective_date > state.last_completed_date)
        ):
            # A pending machine remains due across missed days. This also
            # preserves an explicit manual selection until it is completed.
            desired = state.current_asset
        elif state.last_completed_date and target_date > state.last_completed_date:
            desired = cls._next_after(factory, state.last_completed_asset)
        elif state.current_asset_id in active_ids:
            desired = state.current_asset
        else:
            desired = cls._next_after(factory, state.current_asset or state.last_completed_asset)
        if state.current_asset_id != getattr(desired, "id", None) or state.current_effective_date != target_date:
            asset_changed = state.current_asset_id != getattr(desired, "id", None)
            state.current_asset = desired; state.current_effective_date = target_date
            update_fields = ["current_asset", "current_effective_date", "updated_at"]
            if asset_changed:
                state.manual_selected_by = None; state.manual_selected_at = None
                update_fields.extend(["manual_selected_by", "manual_selected_at"])
            state.save(update_fields=update_fields)
        return desired, state

    @classmethod
    @transaction.atomic
    def select_current_asset(cls, factory, asset, selected_by, target_date=None):
        target_date = target_date or timezone.localdate()
        if not cls.is_maintenance_day(target_date):
            raise ValidationError("يوم الجمعة عطلة الصيانة الأسبوعية ولا يمكن تعيين ماكينة له.")
        if asset.factory_id != factory.id or not asset.is_active or asset.is_archived:
            raise ValidationError("يجب اختيار ماكينة نشطة تابعة للمصنع نفسه.")
        if MaintenanceReport.objects.filter(factory=factory, report_date=target_date).exists():
            raise ValidationError("تم إكمال تقرير هذا اليوم بالفعل ولا يمكن تغيير الماكينة بعد الإرسال.")
        state, _ = FactoryMaintenanceState.objects.select_for_update().get_or_create(factory=factory)
        state.current_asset = asset
        state.current_effective_date = target_date
        state.manual_selected_by = selected_by
        state.manual_selected_at = timezone.now()
        state.order_version += 1
        state.save(update_fields=["current_asset", "current_effective_date", "manual_selected_by", "manual_selected_at", "order_version", "updated_at"])
        logger.info("current_asset_selected factory_id=%s asset_id=%s selected_by=%s", factory.id, asset.id, selected_by.id)
        return state

    @classmethod
    def validate_answers(cls, asset, answers):
        template = cls.template_for(asset)
        expected = {i.id for s in template.sections.all() for i in s.items.all() if i.is_active}
        received = [a["checklist_item_id"] for a in answers]
        if len(received) != len(set(received)): raise ValidationError({"answers": "لا يجوز تكرار بند الفحص."})
        if set(received) != expected: raise ValidationError({"answers": "يجب إرسال جميع بنود قائمة الفحص الصحيحة فقط."})

    @classmethod
    @transaction.atomic
    def upsert_report(cls, supervisor, data):
        existing = MaintenanceReport.objects.select_for_update().filter(client_report_id=data["client_report_id"]).first()
        if existing:
            if existing.supervisor_id != supervisor.id or existing.factory_id != supervisor.factory_id: raise PermissionDenied("لا تملك صلاحية الوصول إلى هذا التقرير.")
            if existing.asset_id != data["asset_id"] or existing.report_date != data["report_date"]: return SyncResult("conflict", existing, "معرّف التقرير مستخدم لبيانات مختلفة.")
            if existing.effectively_locked: return SyncResult("already_synced", existing)
            if data["last_modified_at_device"] <= existing.last_modified_at_device: return SyncResult("already_synced", existing)
            cls.validate_answers(existing.asset, data["answers"]); cls._replace_answers(existing, data["answers"])
            for field in ("started_at_device", "completed_at_device", "last_modified_at_device"): setattr(existing, field, data[field])
            existing.save(update_fields=["started_at_device", "completed_at_device", "last_modified_at_device", "updated_at"])
            logger.info("report_modified report_id=%s supervisor_id=%s", existing.id, supervisor.id)
            return SyncResult("synced", existing)
        if data["report_date"] > timezone.localdate(): return SyncResult("rejected", reason="لا يمكن إرسال تقرير بتاريخ مستقبلي.")
        if not cls.is_maintenance_day(data["report_date"]): return SyncResult("rejected", reason="يوم الجمعة عطلة الصيانة الأسبوعية ولا تُقبل فيه تقارير صيانة.")
        if data["completed_at_device"] < data["started_at_device"]: return SyncResult("rejected", reason="وقت الإكمال يجب ألا يسبق وقت البدء.")
        if data["last_modified_at_device"] < data["started_at_device"]: return SyncResult("rejected", reason="وقت آخر تعديل غير صحيح.")
        asset = Asset.objects.filter(pk=data["asset_id"], factory=supervisor.factory).first()
        if not asset: return SyncResult("rejected", reason="الماكينة غير تابعة للمصنع المخصص للمشرف.")
        due, state = cls.current_asset(supervisor.factory, data["report_date"], lock=True)
        if state.last_completed_date and data["report_date"] <= state.last_completed_date: return SyncResult("conflict", reason="يوجد تقرير أحدث أو مساوٍ لهذا التاريخ في دورة المصنع.")
        if not due: return SyncResult("rejected", reason="لا توجد ماكينات نشطة في المصنع.")
        if due.id != asset.id: return SyncResult("conflict", reason="الماكينة لا تطابق العنصر المطلوب في تسلسل الصيانة لهذا التاريخ.")
        cls.validate_answers(asset, data["answers"])
        report = MaintenanceReport.objects.create(client_report_id=data["client_report_id"], factory=supervisor.factory, asset=asset, supervisor=supervisor, report_date=data["report_date"], started_at_device=data["started_at_device"], completed_at_device=data["completed_at_device"], last_modified_at_device=data["last_modified_at_device"], is_locked=data["report_date"] < timezone.localdate())
        cls._replace_answers(report, data["answers"])
        state.current_asset = asset; state.current_effective_date = report.report_date; state.last_completed_asset = asset; state.last_completed_date = report.report_date; state.manual_selected_by = None; state.manual_selected_at = None
        state.save(update_fields=["current_asset", "current_effective_date", "last_completed_asset", "last_completed_date", "manual_selected_by", "manual_selected_at", "updated_at"])
        logger.info("report_created report_id=%s factory_id=%s asset_id=%s", report.id, report.factory_id, report.asset_id)
        return SyncResult("synced", report)

    @staticmethod
    def _replace_answers(report, answers):
        report.answers.all().delete()
        MaintenanceReportItem.objects.bulk_create([MaintenanceReportItem(report=report, checklist_item_id=a["checklist_item_id"], checked=a["checked"], note=a.get("note", "")) for a in answers])

    @classmethod
    @transaction.atomic
    def reorder(cls, factory, ordered_ids):
        assets = list(Asset.objects.select_for_update().filter(factory=factory, id__in=ordered_ids, is_archived=False))
        if len(assets) != len(ordered_ids): raise ValidationError("قائمة الماكينات غير صحيحة.")
        types = {a.asset_type for a in assets}
        if len(types) != 1: raise ValidationError("يجب ترتيب ماكينات من النوع نفسه معًا.")
        by_id = {a.id: a for a in assets}
        for order, asset_id in enumerate(ordered_ids, 1): by_id[asset_id].sequence_order = order
        Asset.objects.bulk_update(assets, ["sequence_order"])
        state, _ = FactoryMaintenanceState.objects.get_or_create(factory=factory); state.order_version += 1; state.save(update_fields=["order_version", "updated_at"])
        logger.info("asset_order_changed factory_id=%s type=%s", factory.id, next(iter(types)))
