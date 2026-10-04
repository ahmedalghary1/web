from django.urls import path
from . import views

app_name = "production"

urlpatterns = [
    path("", views.home, name="home"),
    path("reports/", views.report_list, name="reports"),
    path("reports/<int:pk>/export.xlsx", views.export_report_excel, name="report_export_excel"),
    path("reports/<int:pk>/", views.report_detail, name="report_detail"),
    path("reports/<int:pk>/confirm-handover/", views.confirm_handover, name="confirm-handover"),
    path("machine-defaults/", views.machine_defaults, name="machine_defaults"),
    path("machine-defaults/<int:asset_id>/edit/", views.machine_default_edit, name="machine_default_edit"),
    path("options/<str:category>/", views.production_options, name="production_options"),
    path("options/<str:category>/add/", views.production_option_form, name="production_option_add"),
    path("options/<str:category>/<int:pk>/edit/", views.production_option_form, name="production_option_edit"),
    path("options/<str:category>/<int:pk>/toggle/", views.production_option_toggle, name="production_option_toggle"),
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
