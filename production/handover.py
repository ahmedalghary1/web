from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from .models import ProductionShiftReport, SupervisorHandoverRoute
from factories.models import Factory
from .shift_rotation import next_supervisor_for, rotation_for


def receiver_for(user, factory, day=None):
    rotation = rotation_for(factory)
    if rotation:
        return next_supervisor_for(user, factory, day, rotation)
    route = SupervisorHandoverRoute.objects.select_related("receiver").filter(supervisor=user).first()
    if route and route.receiver.is_active and route.receiver.factory_id == factory.pk and route.receiver.role in {"PRODUCTION_SUPERVISOR", "GENERAL_SUPERVISOR"} and route.receiver_id != user.pk:
        return route.receiver
    return None


def pending_for(user, factory):
    return ProductionShiftReport.objects.filter(
        factory=factory, handover_to_supervisor=user, status="PENDING_HANDOVER",
        completed_at_device__isnull=False,
    ).exclude(supervisor=user).order_by("created_at", "pk")


@transaction.atomic
def decide_handover(report_id, user, decision, notes):
    factory_id = ProductionShiftReport.objects.values_list("factory_id", flat=True).get(pk=report_id)
    Factory.objects.select_for_update().get(pk=factory_id)
    report = ProductionShiftReport.objects.select_for_update().get(pk=report_id)
    if report.handover_to_supervisor_id != user.pk or report.supervisor_id == user.pk or report.factory_id != user.factory_id:
        raise PermissionDenied("فقط المشرف المستلم المحدد يمكنه مراجعة هذا التقرير.")
    notes = notes.strip()
    if decision not in {"ACCEPT", "REJECT"} or (decision == "REJECT" and not notes):
        raise ValidationError("يجب كتابة سبب عدم القبول.")
    target = "CONFIRMED" if decision == "ACCEPT" else "REJECTED"
    if report.status == target and report.handover_notes == notes:
        return report  # Safe retry after a lost response.
    if report.status != "PENDING_HANDOVER" or report.completed_at_device is None:
        raise ValidationError("التقرير ليس بانتظار المراجعة أو سبق تسجيل القرار.")
    report.status = target
    report.handover_notes = notes
    report.handover_confirmed_at = timezone.now()
    report.save(update_fields=["status", "handover_notes", "handover_confirmed_at", "updated_at"])
    return report
