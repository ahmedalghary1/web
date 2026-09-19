from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from api.views import BatchSyncView, BootstrapView, CurrentAssetSelectionView, CurrentMaintenanceView, LoginView, MeView, ReportCreateView, ReportUpdateView

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="api-login"), path("auth/refresh/", TokenRefreshView.as_view(), name="api-refresh"), path("auth/me/", MeView.as_view(), name="api-me"),
    path("mobile/bootstrap/", BootstrapView.as_view()), path("mobile/current-maintenance/", CurrentMaintenanceView.as_view()), path("mobile/current-maintenance/select/", CurrentAssetSelectionView.as_view()), path("mobile/reports/", ReportCreateView.as_view()), path("mobile/reports/<int:pk>/", ReportUpdateView.as_view()), path("mobile/sync/reports/", BatchSyncView.as_view()),
]
