import math

from rest_framework import status, serializers
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
    ProductionOption,
    MachineProductionDefault,
    ProductionShiftReport,
    MachineProductionEntry,
    ProductionStoppage,
)
from .serializers import (
    ProductSerializer,
    MachineOperatorSerializer,
    ProductionOptionSerializer,
    ProductionAssetSerializer,
    ProductionShiftReportSerializer,
    SyncShiftReportInputSerializer,
    ConfirmHandoverInputSerializer,
)

from .handover import receiver_for, pending_for, decide_handover

class ProductionBootstrapView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if not getattr(user, "can_access_production", True):
            return Response({"detail": "ليس لديك صلاحية الوصول إلى نظام الإنتاج والأعطال."}, status=status.HTTP_403_FORBIDDEN)

        is_admin = getattr(user, "is_admin", user.is_superuser or user.role == "ADMIN")
        all_active_factories = list(Factory.objects.filter(is_active=True).order_by("id"))

        factory = user.factory
        requested_factory_id = request.GET.get("factory") if is_admin else None
        if requested_factory_id:
            matched = next((f for f in all_active_factories if str(f.id) == str(requested_factory_id)), None)
            if matched:
                factory = matched

        if not factory and is_admin:
            factory = all_active_factories[0] if all_active_factories else None

        if not factory:
            return Response({"detail": "لا يوجد مصنع نشط بالنظام."}, status=status.HTTP_400_BAD_REQUEST)

        today = timezone.localdate()

        # 1. Assets with production defaults
        assets = Asset.objects.filter(
            factory=factory, is_active=True, is_archived=False
        ).select_related(
            "production_default", "production_default__default_product", "production_default__default_operator",
            "production_default__default_raw_material", "production_default__default_final_unit",
            "production_default__target_cycle_unit", "production_default__default_packaging",
        ).order_by("sequence_order", "id")

        # 2. Products
        products = Product.objects.filter(factory=factory, is_active=True).order_by("name")

        # 3. Operators
        operators = MachineOperator.objects.filter(factory=factory, is_active=True).order_by("name")

        # 4. Resolve shift info and next supervisor for current user
        user_shift = getattr(user, "shift", None)
        next_shift = None
        next_shift_display = None
        next_supervisor = None

        next_supervisor = receiver_for(user, factory)
        if next_supervisor:
            next_shift = next_supervisor.shift
            next_shift_display = next_supervisor.get_shift_display() if next_shift else None

        pending_handover = pending_for(user, factory).select_related(
            "supervisor", "handover_to_supervisor"
        ).prefetch_related("machine_entries", "stoppages").first()

        # 6. Today's reports
        today_reports = ProductionShiftReport.objects.filter(
            factory=factory,
            report_date=today, supervisor=user
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
            "production_options": ProductionOptionSerializer(
                ProductionOption.objects.filter(factory=factory, is_active=True).order_by("category", "name"), many=True
            ).data,
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

        serializer = SyncShiftReportInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        factory = user.factory
        requested_factory_id = data.get("factory_id")
        if getattr(user, "is_admin", False):
            if requested_factory_id is not None:
                factory = Factory.objects.filter(pk=requested_factory_id, is_active=True).first()
            elif not factory:
                factory = Factory.objects.filter(is_active=True).first()
        elif requested_factory_id is not None and (not factory or requested_factory_id != factory.pk):
            return Response({"detail": "التقرير لا يتبع مصنع المستخدم."}, status=status.HTTP_403_FORBIDDEN)

        if not factory:
            return Response({"detail": "المستخدم غير مربوط بمصنع نشط."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            report_shift = data.get("shift", "FIRST")
            report_status = data.get("status", "PENDING_HANDOVER")

            # Serialize submissions within a factory so a handover cannot race a new draft.
            Factory.objects.select_for_update().get(pk=factory.pk)
            target_handover_supervisor = receiver_for(user, factory)

            report = ProductionShiftReport.objects.filter(client_report_id=data["client_report_id"]).first()
            if report and report.factory_id != factory.pk:
                return Response({"detail": "التقرير لا يتبع المصنع المحدد."}, status=status.HTTP_403_FORBIDDEN)
            if report and report.supervisor_id != user.pk:
                return Response({"detail": "لا يمكنك تعديل تقرير مشرف آخر."}, status=403)
            if report and (report.completed_at_device is not None or report.status in {"CONFIRMED", "REJECTED"}):
                return Response(ProductionShiftReportSerializer(report).data)
            if pending_for(user, factory).exists():
                return Response({"detail": "راجع تقرير المشرف السابق بالموافقة أو عدم القبول أولاً."}, status=409)
            if report_status == "PENDING_HANDOVER" and not target_handover_supervisor:
                return Response({"detail": "يجب تحديد المشرف المستلم من الداشبورد قبل التسليم."}, status=400)
            if report_status == "PENDING_HANDOVER" and not data.get("completed_at_device"):
                return Response({"detail": "وقت نهاية التقرير مطلوب عند التسليم."}, status=400)
            if not report:
                report = ProductionShiftReport.objects.filter(
                    factory=factory,
                    report_date=data["report_date"],
                    shift=report_shift
                ).first()
                if report:
                    return Response(
                        {"detail": "يوجد تقرير مسجل لهذه الوردية. حدّث بيانات التطبيق لفتح التقرير الحالي.",
                         "client_report_id": str(report.client_report_id)},
                        status=status.HTTP_409_CONFLICT,
                    )

            if report and report.status == ProductionShiftReport.Status.CONFIRMED:
                return Response(ProductionShiftReportSerializer(report).data, status=status.HTTP_200_OK)

            if not report:
                report = ProductionShiftReport(
                    client_report_id=data["client_report_id"],
                    factory=factory,
                    supervisor=user,
                    shift=report_shift,
                    report_date=data["report_date"],
                    started_at_device=data.get("started_at_device"),
                    completed_at_device=data.get("completed_at_device"),
                    status=report_status,
                    handover_to_supervisor=target_handover_supervisor,
                    general_notes=data.get("general_notes", ""),
                )
                report.save()
            elif report.status != ProductionShiftReport.Status.CONFIRMED:
                # Update header info if not already confirmed
                report.shift = report_shift
                report.report_date = data["report_date"]
                if data.get("started_at_device"):
                    report.started_at_device = data.get("started_at_device")
                if data.get("completed_at_device"):
                    report.completed_at_device = data.get("completed_at_device")
                report.status = report_status
                if data.get("general_notes") is not None:
                    report.general_notes = data.get("general_notes")
                if report_status == "PENDING_HANDOVER":
                    report.handover_to_supervisor = target_handover_supervisor
                report.save()

            # Process entries (Never delete existing entries if incoming list is empty)
            incoming_entries = data.get("entries", [])
            if incoming_entries:
                existing_entries = {entry.asset_id: entry for entry in report.machine_entries.all()}
                report.machine_entries.all().delete()
                entries_to_create = []
                seen_asset_ids = set()
                for item in incoming_entries:
                    if item["asset_id"] in seen_asset_ids:
                        raise serializers.ValidationError({"asset_id": "الماكينة مكررة في التقرير."})
                    seen_asset_ids.add(item["asset_id"])
                    asset = Asset.objects.filter(id=item["asset_id"], factory=factory).select_related(
                        "production_default", "production_default__default_product", "production_default__default_operator",
                        "production_default__default_raw_material", "production_default__default_final_unit",
                        "production_default__target_cycle_unit", "production_default__default_packaging",
                    ).first()
                    if not asset:
                        raise serializers.ValidationError({"asset_id": "الماكينة غير موجودة في المصنع المحدد."})

                    def selected_option(option_key, expected_category, default=None):
                        option_id = item.get(option_key)
                        if option_id is None:
                            return default
                        option = ProductionOption.objects.filter(
                            pk=option_id, factory=factory, category=expected_category
                        ).first()
                        if option is None:
                            raise serializers.ValidationError({option_key: "الاختيار لا يتبع المصنع أو نوعه غير صحيح."})
                        return option

                    # Detect if product was changed from default
                    default_cfg = getattr(asset, "production_default", None)
                    existing_entry = existing_entries.get(asset.pk)
                    for key, model in (("original_product_id", Product), ("original_operator_id", MachineOperator)):
                        if item.get(key) is not None and not model.objects.filter(pk=item[key], factory=factory).exists():
                            raise serializers.ValidationError({key: "القيمة الأصلية لا تتبع المصنع."})
                    # A draft may have been entered while these choices were still
                    # active. Bootstrap limits new selections; preserve snapshots
                    # from offline clients as long as they belong to this factory.
                    if item.get("product_id") is not None and not Product.objects.filter(pk=item["product_id"], factory=factory).exists():
                        raise serializers.ValidationError({"product_id": "المنتج لا يتبع المصنع."})
                    if item.get("operator_id") is not None and not MachineOperator.objects.filter(pk=item["operator_id"], factory=factory).exists():
                        raise serializers.ValidationError({"operator_id": "العامل لا يتبع المصنع."})
                    default_prod_id = default_cfg.default_product_id if default_cfg else None
                    default_prod_name = default_cfg.default_product.name if (default_cfg and default_cfg.default_product) else ""
                    
                    selected_prod_id = item.get("product_id")
                    selected_prod_name = item.get("product_name", "")
                    
                    prod_changed = item.get("product_changed", False)
                    orig_prod_id = item.get("original_product_id") or default_prod_id
                    orig_prod_name = item.get("original_product_name") or default_prod_name

                    if "product_id" in item and selected_prod_id != default_prod_id:
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

                    if "operator_id" in item and selected_op_id != default_op_id:
                        op_changed = True
                    elif selected_op_name and default_op_name and selected_op_name.strip() != default_op_name.strip():
                        op_changed = True
                    elif orig_op_name and selected_op_name and orig_op_name.strip() != selected_op_name.strip():
                        op_changed = True

                    if op_changed and not orig_op_name:
                        orig_op_name = default_op_name or "الافتراضي غير محدد"

                    def snapshot(field, default):
                        supplied = item.get(field)
                        if supplied is not None:
                            return supplied
                        if existing_entry is not None:
                            return getattr(existing_entry, field)
                        return default

                    original_cavities = snapshot("original_cavities", default_cfg.original_cavities if default_cfg else 1)
                    original_cooling = snapshot("original_cooling_time_seconds", default_cfg.cooling_time_seconds if default_cfg else 0.0)
                    original_cycle = snapshot("original_cycle_time_seconds", default_cfg.cycle_time_seconds if default_cfg else 0.0)
                    actual_cooling = snapshot("cooling_time_seconds", original_cooling)
                    actual_cycle = snapshot("cycle_time_seconds", original_cycle)
                    raw_material_option = selected_option(
                        "raw_material_option_id", ProductionOption.Category.RAW_MATERIAL,
                        default_cfg.default_raw_material if default_cfg else None,
                    )
                    final_unit = selected_option(
                        "final_production_unit_id", ProductionOption.Category.FINAL_UNIT,
                        existing_entry.final_production_unit if existing_entry and existing_entry.final_production_unit_id else (default_cfg.default_final_unit if default_cfg else None),
                    )
                    packaging_option = selected_option(
                        "packaging_option_id", ProductionOption.Category.PACKAGING,
                        default_cfg.default_packaging if default_cfg else None,
                    )
                    entered_quantity = item.get("final_production_quantity")
                    if entered_quantity is None:  # Backward-compatible with installed older APKs.
                        entered_quantity = item.get("final_production_weight_kg", 0.0)
                        unit_name = "كجم"
                        final_weight_kg = entered_quantity
                        final_unit = ProductionOption.objects.filter(
                            factory=factory, category=ProductionOption.Category.FINAL_UNIT, name="كجم", is_active=True
                        ).first()
                    else:
                        final_unit = selected_option(
                            "final_production_unit_id", ProductionOption.Category.FINAL_UNIT,
                            final_unit or ProductionOption.objects.filter(
                                factory=factory, category=ProductionOption.Category.FINAL_UNIT, name="كجم", is_active=True
                            ).first(),
                        )
                        if final_unit is None:
                            raise serializers.ValidationError({"final_production_unit_id": "أضف وحدة إنتاج فعلي من إعدادات الإنتاج أولاً."})
                        unit_name = final_unit.name
                        final_weight_kg = entered_quantity * final_unit.kg_per_unit if final_unit.kg_per_unit is not None else 0.0
                        if not math.isfinite(final_weight_kg) or final_weight_kg < 0:
                            raise serializers.ValidationError({"final_production_quantity": "الكمية أكبر من الحد المسموح أو معادلة تحويل الوحدة غير صحيحة."})
                    raw_material_value = (
                        raw_material_option.name if item.get("raw_material_option_id") is not None
                        else item.get("raw_material", existing_entry.raw_material if existing_entry else (raw_material_option.name if raw_material_option else ""))
                    )
                    packaging_value = (
                        packaging_option.name if item.get("packaging_option_id") is not None
                        else item.get("packaging_type", existing_entry.packaging_type if existing_entry else (packaging_option.name if packaging_option else ""))
                    )
                    if not item.get("dashboard_defaults") and not (existing_entry and existing_entry.dashboard_defaults):
                        raw_material_value = raw_material_value or (existing_entry.raw_material if existing_entry else "") or (raw_material_option.name if raw_material_option else "")
                        packaging_value = packaging_value or (existing_entry.packaging_type if existing_entry else "") or (packaging_option.name if packaging_option else "")
                    fixed_target = default_cfg.target_cycle_production if default_cfg else 0.0
                    fixed_cycle_unit = default_cfg.target_cycle_unit.name if default_cfg and default_cfg.target_cycle_unit else ""

                    dashboard_defaults = (existing_entry.dashboard_defaults if existing_entry and existing_entry.dashboard_defaults
                                          else item.get("dashboard_defaults", ""))
                    if dashboard_defaults:
                        import json
                        baseline = json.loads(dashboard_defaults)
                        orig_prod_name = baseline["product_name"]
                        orig_op_name = baseline["operator_name"]
                        prod_changed = selected_prod_name.strip() != orig_prod_name.strip()
                        op_changed = selected_op_name.strip() != orig_op_name.strip()
                        if existing_entry:
                            orig_prod_id = existing_entry.original_product_id
                            orig_op_id = existing_entry.original_operator_id
                            fixed_target = existing_entry.target_cycle_production
                            fixed_cycle_unit = existing_entry.target_cycle_unit_name

                    entries_to_create.append(MachineProductionEntry(
                        report=report,
                        asset=asset,
                        dashboard_defaults=dashboard_defaults,
                        operator_id=selected_op_id,
                        operator_name=selected_op_name,
                        original_operator_id=orig_op_id,
                        original_operator_name=orig_op_name,
                        operator_changed=op_changed,
                        product_id=selected_prod_id,
                        product_name=selected_prod_name,
                        original_product_id=orig_prod_id,
                        original_product_name=orig_prod_name,
                        product_changed=prod_changed,
                        original_cavities=original_cavities,
                        current_cavities=snapshot("current_cavities", original_cavities),
                        operation_mode=item.get("operation_mode", "AUTO"),
                        original_cooling_time_seconds=original_cooling,
                        original_cycle_time_seconds=original_cycle,
                        cooling_time_seconds=actual_cooling,
                        cycle_time_seconds=actual_cycle,
                        raw_material=raw_material_value,
                        final_production_weight_kg=final_weight_kg,
                        final_production_quantity=entered_quantity,
                        final_production_unit=final_unit,
                        final_production_unit_name=unit_name,
                        target_cycle_production=fixed_target,
                        target_cycle_unit_name=fixed_cycle_unit,
                        packaging_type=packaging_value,
                        notes=item.get("notes", ""),
                    ))

                if entries_to_create:
                    MachineProductionEntry.objects.bulk_create(entries_to_create)

            # Process stoppages
            incoming_stoppages = data.get("stoppages", [])
            if incoming_stoppages:
                report.stoppages.all().delete()
                stoppages_to_create = []
                for stop in incoming_stoppages:
                    asset_id = stop.get("asset_id")
                    asset = Asset.objects.filter(id=asset_id, factory=factory).first() if asset_id else None
                    if asset_id and asset is None:
                        raise serializers.ValidationError({"asset_id": "ماكينة التوقف لا تتبع المصنع المحدد."})
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
        if not getattr(user, "is_admin", False):
            query["factory"] = user.factory

        report = ProductionShiftReport.objects.filter(**query).first()

        if not report:
            return Response({"detail": "تقرير الوردية غير موجود."}, status=status.HTTP_404_NOT_FOUND)

        report = decide_handover(report.pk, user, data["decision"], data["handover_notes"])
        return Response(ProductionShiftReportSerializer(report).data)
