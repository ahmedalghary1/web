from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db import transaction
from drf_spectacular.utils import extend_schema

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
from .serializers import (
    ProductSerializer,
    MachineOperatorSerializer,
    ProductionAssetSerializer,
    ProductionShiftReportSerializer,
    SyncShiftReportInputSerializer,
    ConfirmHandoverInputSerializer,
)

class ProductionBootstrapView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if not getattr(user, "can_access_production", True):
            return Response({"detail": "ليس لديك صلاحية الوصول إلى نظام الإنتاج والأعطال."}, status=status.HTTP_403_FORBIDDEN)

        is_admin = getattr(user, "is_admin", user.is_superuser or user.role == "ADMIN")
        all_active_factories = list(Factory.objects.filter(is_active=True).order_by("id"))

        factory = user.factory
        requested_factory_id = request.GET.get("factory")
        if requested_factory_id:
            matched = next((f for f in all_active_factories if str(f.id) == str(requested_factory_id)), None)
            if matched:
                factory = matched

        if not factory:
            factory = all_active_factories[0] if all_active_factories else None

        if not factory:
            return Response({"detail": "لا يوجد مصنع نشط بالنظام."}, status=status.HTTP_400_BAD_REQUEST)

        today = timezone.localdate()

        # 1. Assets with production defaults
        assets = Asset.objects.filter(
            factory=factory, is_active=True, is_archived=False
        ).select_related("production_default", "production_default__default_product", "production_default__default_operator").order_by("sequence_order", "id")

        # 2. Products
        products = Product.objects.filter(factory=factory, is_active=True).order_by("name")

        # 3. Operators
        operators = MachineOperator.objects.filter(factory=factory, is_active=True).order_by("name")

        # 4. Resolve shift info and next supervisor for current user
        user_shift = getattr(user, "shift", None)
        next_shift = None
        next_shift_display = None
        next_supervisor = None

        if user_shift:
            next_shift = user.next_shift
            next_shift_display = user.Shift(next_shift).label if next_shift else None
            next_supervisor = user.get_next_shift_supervisor()

        # 5. Pending handover report targeted to this incoming supervisor:
        pending_handover = None
        if user_shift:
            prev_shift = user.previous_shift
            # Priority 1: Reports from the previous shift of this factory awaiting handover
            pending_handover = ProductionShiftReport.objects.filter(
                factory=factory,
                status=ProductionShiftReport.Status.PENDING_HANDOVER,
                shift=prev_shift
            ).exclude(supervisor=user).select_related("supervisor", "handover_to_supervisor").prefetch_related("machine_entries", "stoppages").first()

            if not pending_handover:
                # Priority 2: Directly assigned to this user
                pending_handover = ProductionShiftReport.objects.filter(
                    factory=factory,
                    status=ProductionShiftReport.Status.PENDING_HANDOVER,
                    handover_to_supervisor=user
                ).exclude(supervisor=user).select_related("supervisor", "handover_to_supervisor").prefetch_related("machine_entries", "stoppages").first()

        if not pending_handover:
            # Fallback for admin or general supervisors without a fixed shift
            pending_handover = ProductionShiftReport.objects.filter(
                factory=factory,
                status=ProductionShiftReport.Status.PENDING_HANDOVER
            ).exclude(supervisor=user).select_related("supervisor", "handover_to_supervisor").prefetch_related("machine_entries", "stoppages").first()

        # 6. Today's reports
        today_reports = ProductionShiftReport.objects.filter(
            factory=factory,
            report_date=today
        ).select_related("supervisor", "handover_to_supervisor").prefetch_related("machine_entries", "stoppages").order_by("-created_at")

        factories_list = [
            {"id": f.id, "name": f.name, "code": f.code}
            for f in all_active_factories
        ]

        payload = {
            "server_date": str(today),
            "timezone": "Africa/Cairo",
            "factory": {
                "id": factory.id,
                "name": factory.name,
                "code": factory.code,
            },
            "factories": factories_list,
            "user": {
                "id": user.id,
                "phone": user.phone,
                "name": user.display_name,
                "role": user.role,
                "shift": user_shift,
                "shift_display": user.get_shift_display() if user_shift else None,
                "next_shift": next_shift,
                "next_shift_display": next_shift_display,
                "next_shift_supervisor": {
                    "id": next_supervisor.id,
                    "name": next_supervisor.display_name,
                    "phone": next_supervisor.phone,
                } if next_supervisor else None,
            },
            "assets": ProductionAssetSerializer(assets, many=True).data,
            "products": ProductSerializer(products, many=True).data,
            "operators": MachineOperatorSerializer(operators, many=True).data,
            "pending_handover": ProductionShiftReportSerializer(pending_handover).data if pending_handover else None,
            "today_reports": ProductionShiftReportSerializer(today_reports, many=True).data,
        }
        return Response(payload)


class ProductionSyncReportView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=SyncShiftReportInputSerializer, responses={200: ProductionShiftReportSerializer})
    def post(self, request):
        user = request.user
        if not getattr(user, "can_access_production", True):
            return Response({"detail": "ليس لديك صلاحية الوصول إلى نظام الإنتاج والأعطال."}, status=status.HTTP_403_FORBIDDEN)

        factory = user.factory
        if not factory and getattr(user, "is_admin", False):
            factory = Factory.objects.filter(is_active=True).first()

        if not factory:
            return Response({"detail": "المستخدم غير مربوط بمصنع."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = SyncShiftReportInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            report_shift = data.get("shift", "FIRST")
            report_status = data.get("status", "PENDING_HANDOVER")

            target_handover_supervisor = None
            if report_status == ProductionShiftReport.Status.PENDING_HANDOVER:
                cycle_next = {
                    "FIRST": "SECOND",
                    "SECOND": "THIRD",
                    "THIRD": "FIRST",
                }.get(report_shift, "SECOND")
                target_handover_supervisor = User.objects.filter(
                    factory=factory,
                    shift=cycle_next,
                    is_active=True
                ).first()

            report, created = ProductionShiftReport.objects.get_or_create(
                client_report_id=data["client_report_id"],
                defaults={
                    "factory": factory,
                    "supervisor": user,
                    "shift": report_shift,
                    "report_date": data["report_date"],
                    "started_at_device": data.get("started_at_device"),
                    "completed_at_device": data.get("completed_at_device"),
                    "status": report_status,
                    "handover_to_supervisor": target_handover_supervisor,
                    "general_notes": data.get("general_notes", ""),
                }
            )

            if not created and report.status != ProductionShiftReport.Status.CONFIRMED:
                # Update header info if not already confirmed
                report.shift = data.get("shift", report.shift)
                report.report_date = data.get("report_date", report.report_date)
                report.started_at_device = data.get("started_at_device", report.started_at_device)
                report.completed_at_device = data.get("completed_at_device", report.completed_at_device)
                report.status = data.get("status", report.status)
                report.general_notes = data.get("general_notes", report.general_notes)
                if not report.handover_to_supervisor and target_handover_supervisor:
                    report.handover_to_supervisor = target_handover_supervisor
                report.save()

            # Clear old entries & stoppages for idempotency
            report.machine_entries.all().delete()
            report.stoppages.all().delete()

            # Re-create entries
            entries_to_create = []
            for item in data.get("entries", []):
                asset = Asset.objects.filter(id=item["asset_id"], factory=report.factory).first()
                if not asset:
                    continue

                # Detect if product was changed from default
                default_cfg = getattr(asset, "production_default", None)
                default_prod_id = default_cfg.default_product_id if default_cfg else None
                default_prod_name = default_cfg.default_product.name if (default_cfg and default_cfg.default_product) else ""
                
                selected_prod_id = item.get("product_id")
                selected_prod_name = item.get("product_name", "")
                
                prod_changed = item.get("product_changed", False)
                orig_prod_id = item.get("original_product_id") or default_prod_id
                orig_prod_name = item.get("original_product_name") or default_prod_name

                if selected_prod_id and default_prod_id and selected_prod_id != default_prod_id:
                    prod_changed = True
                elif selected_prod_name and default_prod_name and selected_prod_name.strip() != default_prod_name.strip():
                    prod_changed = True
                elif orig_prod_name and selected_prod_name and orig_prod_name.strip() != selected_prod_name.strip():
                    prod_changed = True

                if prod_changed and not orig_prod_name:
                    orig_prod_name = default_prod_name or "الافتراضي غير محدد"

                # Detect if operator was changed from default
                default_op_id = default_cfg.default_operator_id if default_cfg else None
                default_op_name = default_cfg.default_operator.name if (default_cfg and default_cfg.default_operator) else ""
                
                selected_op_id = item.get("operator_id")
                selected_op_name = item.get("operator_name", "")
                
                op_changed = item.get("operator_changed", False)
                orig_op_id = item.get("original_operator_id") or default_op_id
                orig_op_name = item.get("original_operator_name") or default_op_name

                if selected_op_id and default_op_id and selected_op_id != default_op_id:
                    op_changed = True
                elif selected_op_name and default_op_name and selected_op_name.strip() != default_op_name.strip():
                    op_changed = True
                elif orig_op_name and selected_op_name and orig_op_name.strip() != selected_op_name.strip():
                    op_changed = True

                if op_changed and not orig_op_name:
                    orig_op_name = default_op_name or "الافتراضي غير محدد"

                actual_cooling = item.get("cooling_time_seconds")
                actual_cycle = item.get("cycle_time_seconds")
                actual_target = item.get("target_cycle_production")

                entries_to_create.append(MachineProductionEntry(
                    report=report,
                    asset=asset,
                    operator_id=selected_op_id,
                    operator_name=selected_op_name,
                    original_operator_id=orig_op_id if op_changed else None,
                    original_operator_name=orig_op_name if op_changed else "",
                    operator_changed=op_changed,
                    product_id=selected_prod_id,
                    product_name=selected_prod_name,
                    original_product_id=orig_prod_id if prod_changed else None,
                    original_product_name=orig_prod_name if prod_changed else "",
                    product_changed=prod_changed,
                    original_cavities=default_cfg.original_cavities if default_cfg else item.get("original_cavities", 1),
                    current_cavities=item.get("current_cavities", 1),
                    operation_mode=item.get("operation_mode", "AUTO"),
                    cooling_time_seconds=actual_cooling if (actual_cooling is not None and actual_cooling > 0) else (default_cfg.cooling_time_seconds if default_cfg else 0.0),
                    cycle_time_seconds=actual_cycle if (actual_cycle is not None and actual_cycle > 0) else (default_cfg.cycle_time_seconds if default_cfg else 0.0),
                    raw_material=item.get("raw_material", ""),
                    final_production_weight_kg=item.get("final_production_weight_kg", 0.0),
                    target_cycle_production=actual_target if (actual_target is not None and actual_target > 0) else (default_cfg.target_cycle_production if default_cfg else 0.0),
                    packaging_type=item.get("packaging_type", ""),
                    notes=item.get("notes", ""),
                ))

            if entries_to_create:
                MachineProductionEntry.objects.bulk_create(entries_to_create)

            # Re-create stoppages
            stoppages_to_create = []
            for stop in data.get("stoppages", []):
                asset_id = stop.get("asset_id")
                asset = Asset.objects.filter(id=asset_id, factory=report.factory).first() if asset_id else None
                stoppages_to_create.append(ProductionStoppage(
                    report=report,
                    asset=asset,
                    stoppage_type=stop.get("stoppage_type", "MACHINE_BREAKDOWN"),
                    description=stop.get("description", ""),
                    duration_minutes=stop.get("duration_minutes", 0),
                    action_taken=stop.get("action_taken", ""),
                ))

            if stoppages_to_create:
                ProductionStoppage.objects.bulk_create(stoppages_to_create)

        result = ProductionShiftReport.objects.select_related(
            "supervisor", "handover_to_supervisor"
        ).prefetch_related("machine_entries", "stoppages").get(id=report.id)

        return Response(ProductionShiftReportSerializer(result).data, status=status.HTTP_200_OK)


class ProductionConfirmHandoverView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ConfirmHandoverInputSerializer, responses={200: ProductionShiftReportSerializer})
    def post(self, request):
        user = request.user
        if not getattr(user, "can_access_production", True):
            return Response({"detail": "ليس لديك صلاحية الوصول إلى نظام الإنتاج والأعطال."}, status=status.HTTP_403_FORBIDDEN)

        serializer = ConfirmHandoverInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        query = {"client_report_id": data["client_report_id"]}
        if not getattr(user, "is_admin", False) and user.factory:
            query["factory"] = user.factory

        report = ProductionShiftReport.objects.filter(**query).first()

        if not report:
            return Response({"detail": "تقرير الوردية غير موجود."}, status=status.HTTP_404_NOT_FOUND)

        report.status = ProductionShiftReport.Status.CONFIRMED
        report.handover_to_supervisor = request.user
        report.handover_confirmed_at = timezone.now()
        if data.get("handover_notes"):
            report.handover_notes = data["handover_notes"]
        report.save()

        return Response(ProductionShiftReportSerializer(report).data)
