from django.urls import path
from .api import RegisterView, LatestView, HeartbeatView, DownloadView

app_name = "updates"
urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("latest/", LatestView.as_view(), name="latest"),
    path("heartbeat/", HeartbeatView.as_view(), name="heartbeat"),
    path("releases/<int:pk>/download/", DownloadView.as_view(), name="download"),
]
