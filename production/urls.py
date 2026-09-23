from django.urls import path
from . import views

app_name = "production"

urlpatterns = [
    path("", views.home, name="home"),
    path("reports/", views.report_list, name="reports"),
    path("reports/<int:pk>/", views.report_detail, name="report_detail"),
    path("reports/<int:pk>/confirm-handover/", views.confirm_handover, name="confirm-handover"),
    path("machine-defaults/", views.machine_defaults, name="machine_defaults"),
    path("machine-defaults/<int:asset_id>/edit/", views.machine_default_edit, name="machine_default_edit"),
    path("products/", views.product_list, name="products"),
    path("products/add/", views.product_form, name="product_add"),
    path("products/<int:pk>/edit/", views.product_form, name="product_edit"),
    path("products/<int:pk>/toggle/", views.product_toggle, name="product_toggle"),
    path("operators/", views.operator_list, name="operators"),
    path("operators/add/", views.operator_form, name="operator_add"),
    path("operators/<int:pk>/edit/", views.operator_form, name="operator_edit"),
    path("operators/<int:pk>/toggle/", views.operator_toggle, name="operator_toggle"),
    path("stoppages/", views.stoppage_list, name="stoppages"),
]
