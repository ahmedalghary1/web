from django.urls import path
from dashboard import views
app_name = "dashboard"
urlpatterns = [
    path("", views.home, name="home"),
    path("factories/", views.factories, name="factories"),
    path("assets/", views.asset_list, name="assets"),
    path("assets/add/", views.asset_form, name="asset-add"),
    path("assets/<int:pk>/edit/", views.asset_form, name="asset-edit"),
    path("assets/<int:pk>/archive/", views.asset_archive, name="asset-archive"),
    path("assets/reorder/", views.asset_reorder, name="asset-reorder"),
    path("daily/", views.daily, name="daily"),
    path("daily/<int:factory_id>/select-asset/", views.select_daily_asset, name="daily-select-asset"),
    path("reports/", views.report_list, name="reports"),
    path("reports/<int:pk>/", views.report_detail, name="report_detail"),
    path("reports/<int:pk>/edit/", views.report_edit, name="report_edit"),
    path("users/", views.user_list, name="users"),
    path("users/add/", views.user_form, name="user-add"),
    path("users/<int:pk>/edit/", views.user_form, name="user-edit"),
    path("account/", views.account, name="account"),
    path("checklists/", views.checklist_list, name="checklists"),
    path("checklists/add/", views.checklist_form, name="checklist-add"),
    path("checklists/<int:pk>/edit/", views.checklist_form, name="checklist-edit"),
    path("checklists/<int:pk>/builder/", views.checklist_builder, name="checklist-builder"),
]
