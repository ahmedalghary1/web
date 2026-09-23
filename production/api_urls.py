from django.urls import path
from .api_views import (
    ProductionBootstrapView,
    ProductionSyncReportView,
    ProductionConfirmHandoverView,
)

app_name = "production-api"

urlpatterns = [
    path("bootstrap/", ProductionBootstrapView.as_view(), name="bootstrap"),
    path("sync/shift-reports/", ProductionSyncReportView.as_view(), name="sync-shift-reports"),
    path("reports/confirm-handover/", ProductionConfirmHandoverView.as_view(), name="confirm-handover"),
]
