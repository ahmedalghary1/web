import logging
from django.db import IntegrityError
from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from drf_spectacular.utils import OpenApiTypes, extend_schema
from api.permissions import IsMaintenanceSupervisor
from api.serializers import BatchSyncSerializer, ChecklistTemplateSerializer, CurrentAssetSelectionSerializer, LoginSerializer, ReportInputSerializer, ReportSerializer, UserSerializer, AssetSerializer
from assets.models import Asset
from maintenance.models import ChecklistItem, ChecklistTemplate, MaintenanceReport
from maintenance.services.cycle import MaintenanceCycleService

logger = logging.getLogger("api")
class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer; throttle_scope = "login"
class MeView(APIView):
    serializer_class = UserSerializer
    @extend_schema(responses=UserSerializer)
    def get(self, request): return Response(UserSerializer(request.user).data)

def current_payload(user):
    today = timezone.localdate(); asset, state = MaintenanceCycleService.current_asset(user.factory, today)
    report = MaintenanceReport.objects.filter(factory=user.factory, report_date=today).select_related("asset", "supervisor").prefetch_related("answers__checklist_item").first()
    if report: asset = report.asset
    active_assets = MaintenanceCycleService.active_assets(user.factory)
    position = next((index for index, item in enumerate(active_assets, 1) if asset and item.id == asset.id), 0)
    return {"server_date": today, "timezone": "Africa/Cairo", "factory": {"id": user.factory_id, "name": user.factory.name}, "asset": AssetSerializer(asset).data if asset else None, "checklist_template": ChecklistTemplateSerializer(MaintenanceCycleService.template_for(asset)).data if asset else None, "is_reported": bool(report), "report": ReportSerializer(report).data if report else None, "order_version": state.order_version, "is_maintenance_day": MaintenanceCycleService.is_maintenance_day(today), "selection_mode": "manual" if state.manual_selected_by_id and asset and state.current_asset_id == asset.id else "automatic", "cycle_position": position, "cycle_total": len(active_assets)}
class CurrentMaintenanceView(APIView):
    permission_classes = [IsMaintenanceSupervisor]
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request): return Response(current_payload(request.user))
class CurrentAssetSelectionView(APIView):
    permission_classes = [IsMaintenanceSupervisor]
    serializer_class = CurrentAssetSelectionSerializer
    @extend_schema(request=CurrentAssetSelectionSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = self.serializer_class(data=request.data); serializer.is_valid(raise_exception=True)
        asset = Asset.objects.filter(pk=serializer.validated_data["asset_id"], factory=request.user.factory).first()
        if not asset: return Response({"detail": "الماكينة غير تابعة للمصنع المخصص لك."}, status=400)
        try: MaintenanceCycleService.select_current_asset(request.user.factory, asset, request.user)
        except Exception as exc:
            detail = getattr(exc, "detail", str(exc))
            if isinstance(detail, list): detail = str(detail[0])
            return Response({"detail": detail}, status=400)
        return Response(current_payload(request.user))
class BootstrapView(APIView):
    permission_classes = [IsMaintenanceSupervisor]
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        active_items = Prefetch("sections__items", queryset=ChecklistItem.objects.filter(is_active=True))
        templates_qs = ChecklistTemplate.objects.filter(is_active=True).prefetch_related(active_items)

        payload = current_payload(request.user)
        payload.update(
            user=UserSerializer(request.user).data,
            active_assets=AssetSerializer(MaintenanceCycleService.active_assets(request.user.factory), many=True).data,
            checklist_templates=ChecklistTemplateSerializer(templates_qs, many=True).data
        )
        return Response(payload)
class ReportUpsertView(APIView):
    permission_classes = [IsMaintenanceSupervisor]
    serializer_class = ReportInputSerializer
    def post(self, request): return self._save(request)
    def put(self, request, pk=None):
        if pk:
            report = MaintenanceReport.objects.filter(pk=pk, supervisor=request.user).first()
            if not report: return Response({"detail": "التقرير غير موجود."}, status=404)
            mutable = request.data.copy(); mutable["client_report_id"] = str(report.client_report_id)
            serializer = ReportInputSerializer(data=mutable)
        else: serializer = ReportInputSerializer(data=request.data)
        return self._validated_save(request, serializer)
    def _save(self, request): return self._validated_save(request, ReportInputSerializer(data=request.data))
    def _validated_save(self, request, serializer):
        serializer.is_valid(raise_exception=True)
        try: result = MaintenanceCycleService.upsert_report(request.user, serializer.validated_data)
        except IntegrityError:
            logger.warning("sync_conflict supervisor_id=%s", request.user.id); return Response({"status": "conflict", "reason": "يوجد تقرير لهذا المصنع في التاريخ نفسه."}, status=409)
        code = status.HTTP_201_CREATED if result.status == "synced" else (status.HTTP_409_CONFLICT if result.status == "conflict" else status.HTTP_400_BAD_REQUEST if result.status == "rejected" else status.HTTP_200_OK)
        return Response({"status": result.status, "reason": result.reason, "report": ReportSerializer(result.report).data if result.report else None}, status=code)
class BatchSyncView(APIView):
    permission_classes = [IsMaintenanceSupervisor]
    serializer_class = BatchSyncSerializer
    def post(self, request):
        serializer = BatchSyncSerializer(data=request.data); serializer.is_valid(raise_exception=True); results = []
        for item in serializer.validated_data["reports"]:
            try:
                result = MaintenanceCycleService.upsert_report(request.user, item); results.append({"client_report_id": str(item["client_report_id"]), "status": result.status, "reason": result.reason, "report_id": result.report.id if result.report else None})
            except Exception as exc:
                logger.exception("batch_sync_error supervisor_id=%s", request.user.id)
                reason = getattr(exc, "detail", "تعذر مزامنة التقرير.")
                if isinstance(reason, dict): reason = " ".join([str(v[0]) if isinstance(v, list) else str(v) for v in reason.values()])
                elif isinstance(reason, list): reason = str(reason[0])
                else: reason = str(reason)
                results.append({"client_report_id": str(item["client_report_id"]), "status": "rejected", "reason": reason})
        return Response({"results": results, "current_maintenance": current_payload(request.user), "server_date": timezone.localdate()})

class ReportCreateView(ReportUpsertView):
    http_method_names = ["post", "options"]
class ReportUpdateView(ReportUpsertView):
    http_method_names = ["put", "options"]
