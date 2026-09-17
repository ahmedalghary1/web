from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from dashboard.forms import PhoneAuthenticationForm
urlpatterns = [path("admin/", admin.site.urls), path("login/", auth_views.LoginView.as_view(template_name="registration/login.html", authentication_form=PhoneAuthenticationForm), name="login"), path("logout/", auth_views.LogoutView.as_view(), name="logout"), path("", include("dashboard.urls")), path("api/v1/", include("api.urls")), path("api/schema/", SpectacularAPIView.as_view(), name="schema"), path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui")]
