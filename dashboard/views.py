from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from assets.models import Asset
from dashboard.forms import AccountUpdateForm, AssetForm, SupervisorForm
from factories.models import Factory
from maintenance.models import MaintenanceReport, MaintenanceReportItem
from maintenance.services.cycle import MaintenanceCycleService

admin_required = user_passes_test(lambda u: u.is_authenticated and (getattr(u, "is_admin", False) or u.is_superuser or u.role == User.Role.ADMIN))

@login_required
@admin_required
def home(request):
    if not getattr(request.user, "can_access_maintenance", True):
        if getattr(request.user, "can_access_production", False):
            return redirect("production:home")
        messages.error(request, "ليس لديك صلاحية الوصول إلى نظام الصيانة.")
        return redirect("login")

    today = timezone.localdate(); cards = []; missed_count = 0; is_maintenance_day = MaintenanceCycleService.is_maintenance_day(today)
    is_admin = getattr(request.user, "is_admin", False)
    if is_admin:
        factories = Factory.objects.filter(is_active=True)
    else:
        factories = Factory.objects.filter(pk=request.user.factory_id, is_active=True) if request.user.factory_id else Factory.objects.none()

    for factory in factories:
        asset, _ = MaintenanceCycleService.current_asset(factory, today)
        report = MaintenanceReport.objects.filter(factory=factory, report_date=today).select_related("asset", "supervisor").first()
        cards.append({"factory": factory, "asset": report.asset if report else asset, "report": report})
        dates = set(MaintenanceReport.objects.filter(factory=factory, report_date__lt=today).values_list("report_date", flat=True))
        if dates:
            cursor = min(dates)
            while cursor < today:
                if MaintenanceCycleService.is_maintenance_day(cursor) and cursor not in dates: missed_count += 1
                cursor += timedelta(days=1)

    reports_qs = MaintenanceReport.objects.select_related("factory", "asset", "supervisor").prefetch_related("answers")
    notes_qs = MaintenanceReportItem.objects.exclude(note="").select_related("report__factory", "report__asset", "checklist_item")
    completed_qs = MaintenanceReport.objects.filter(report_date__gte=today-timedelta(days=30))

    if not is_admin and request.user.factory_id:
        reports_qs = reports_qs.filter(factory_id=request.user.factory_id)
        notes_qs = notes_qs.filter(report__factory_id=request.user.factory_id)
        completed_qs = completed_qs.filter(factory_id=request.user.factory_id)

    reports = reports_qs.all()[:8]
    notes = notes_qs.order_by("-report__created_at")[:6]
    return render(request, "dashboard/home.html", {
        "cards": cards,
        "reports": reports,
        "notes": notes,
        "missed_count": missed_count,
        "completed_count": completed_qs.count(),
        "is_maintenance_day": is_maintenance_day,
        "is_admin": is_admin,
    })
@login_required
@admin_required
def asset_list(request):
    qs = Asset.objects.select_related("factory").filter(is_archived=False)
    if request.GET.get("factory"): qs = qs.filter(factory_id=request.GET["factory"])
    if request.GET.get("asset_type"): qs = qs.filter(asset_type=request.GET["asset_type"])
    if request.GET.get("q"): qs = qs.filter(asset_code__icontains=request.GET["q"])
    return render(request, "dashboard/assets.html", {"assets": qs, "factories": Factory.objects.all(), "types": Asset.Type.choices})
@login_required
@admin_required
def asset_form(request, pk=None):
    obj = get_object_or_404(Asset, pk=pk, is_archived=False) if pk else None
    form = AssetForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم حفظ بيانات الماكينة بنجاح.")
        return redirect("dashboard:assets")
    delete_url = reverse("dashboard:asset-delete", args=[obj.pk]) if obj else None
    return render(request, "dashboard/form.html", {
        "form": form,
        "title": "تعديل ماكينة" if obj else "إضافة ماكينة",
        "delete_url": delete_url,
    })
@login_required
@admin_required
def asset_archive(request, pk):
    if request.method == "POST":
        asset = get_object_or_404(Asset, pk=pk)
        asset.is_archived = True
        asset.is_active = False
        asset.save()
        messages.success(request, "تمت أرشفة الماكينة مع الحفاظ على سجلها التاريخي.")
    return redirect("dashboard:assets")
@login_required
@admin_required
def asset_delete(request, pk):
    asset = get_object_or_404(Asset, pk=pk)
    factory = asset.factory
    asset_code = asset.asset_code
    reports_count = asset.reports.count()
    emergency_count = asset.emergency_maintenances.count()

    if request.method == "POST":
        force = request.POST.get("force") == "1"
        if (reports_count > 0 or emergency_count > 0) and not force:
            return render(request, "dashboard/asset_delete_confirm.html", {
                "asset": asset,
                "reports_count": reports_count,
                "emergency_count": emergency_count,
            })

        with transaction.atomic():
            from maintenance.models import FactoryMaintenanceState
            state = FactoryMaintenanceState.objects.filter(factory=factory).first()
            if state:
                changed = False
                if state.current_asset_id == asset.id:
                    state.current_asset = None
                    changed = True
                if state.last_completed_asset_id == asset.id:
                    state.last_completed_asset = None
                    changed = True
                if changed:
                    state.save(update_fields=["current_asset", "last_completed_asset"])

            if emergency_count > 0:
                asset.emergency_maintenances.all().delete()
            if reports_count > 0:
                asset.reports.all().delete()

            asset.delete()
            MaintenanceCycleService.current_asset(factory)

        messages.success(request, f"تم حذف الماكينة {asset_code} بنجاح.")
        return redirect("dashboard:assets")

    return render(request, "dashboard/asset_delete_confirm.html", {
        "asset": asset,
        "reports_count": reports_count,
        "emergency_count": emergency_count,
    })
@login_required
@admin_required
def asset_reorder(request):
    if request.method != "POST": return JsonResponse({"detail": "طريقة الطلب غير مسموحة."}, status=405)
    try:
        ids = [int(v) for v in request.POST.getlist("ids[]")]; factory = Factory.objects.get(pk=request.POST["factory"]); MaintenanceCycleService.reorder(factory, ids); return JsonResponse({"message": "تم تحديث الترتيب."})
    except Exception as exc: return JsonResponse({"detail": str(exc)}, status=400)
@login_required
def report_list(request):
    if not getattr(request.user, "can_access_maintenance", True):
        if getattr(request.user, "can_access_production", False):
            return redirect("production:reports")
        messages.error(request, "ليس لديك صلاحية الوصول إلى تقارير الصيانة.")
        return redirect("login")

    is_admin = getattr(request.user, "is_admin", False)
    qs = MaintenanceReport.objects.select_related("factory", "asset", "supervisor").annotate(
        checked_count=Count("answers", filter=Q(answers__checked=True), distinct=True),
        unchecked_count=Count("answers", filter=Q(answers__checked=False), distinct=True),
        emergency_count=Count("emergency_items", distinct=True)
    ).order_by("-report_date", "-created_at")

    if not is_admin:
        qs = qs.filter(factory_id=request.user.factory_id)
    elif request.GET.get("factory"):
        qs = qs.filter(factory_id=request.GET["factory"])

    for field, param in {"asset__asset_type":"asset_type","supervisor_id":"supervisor","report_date":"date"}.items():
        if request.GET.get(param): qs = qs.filter(**{field: request.GET[param]})
    if request.GET.get("asset_code"): qs = qs.filter(asset__asset_code__icontains=request.GET["asset_code"])
    if request.GET.get("date_from"): qs = qs.filter(report_date__gte=request.GET["date_from"])
    if request.GET.get("date_to"): qs = qs.filter(report_date__lte=request.GET["date_to"])
    reports = Paginator(qs, 25).get_page(request.GET.get("page"))
    filters = request.GET.copy(); filters.pop("page", None)
    factories_list = Factory.objects.all() if is_admin else ([request.user.factory] if request.user.factory else [])
    return render(request, "dashboard/reports.html", {
        "reports": reports,
        "factories": factories_list,
        "supervisors": User.objects.filter(role__in=[User.Role.MAINTENANCE_SUPERVISOR, User.Role.GENERAL_SUPERVISOR]),
        "types": Asset.Type.choices,
        "filter_query": filters.urlencode(),
        "is_admin": is_admin
    })

@login_required
def report_detail(request, pk):
    if not getattr(request.user, "can_access_maintenance", True):
        messages.error(request, "ليس لديك صلاحية الوصول إلى هذا التقرير.")
        return redirect("login")

    report_qs = MaintenanceReport.objects.select_related("factory", "asset", "supervisor").prefetch_related("answers__checklist_item__section", "emergency_items__asset")
    is_admin = getattr(request.user, "is_admin", False)
    if not is_admin:
        report = get_object_or_404(report_qs, pk=pk, factory_id=request.user.factory_id)
    else:
        report = get_object_or_404(report_qs, pk=pk)

    sections = {}
    for answer in report.answers.all(): sections.setdefault(answer.checklist_item.section.name, []).append(answer)
    return render(request, "dashboard/report_detail.html", {
        "report": report,
        "sections": sections.items(),
        "emergency_items": report.emergency_items.all(),
        "is_admin": is_admin
    })

@login_required
@admin_required
def report_edit(request, pk):
    report = get_object_or_404(MaintenanceReport.objects.select_related("factory", "asset", "supervisor").prefetch_related("answers__checklist_item__section", "emergency_items__asset"), pk=pk)
    if request.method == "POST":
        with transaction.atomic():
            for answer in report.answers.all():
                checked_str = request.POST.get(f"checked_{answer.id}")
                answer.checked = (checked_str == "on")
                answer.note = request.POST.get(f"note_{answer.id}", "")
                answer.save()
            report.cleaner_name = request.POST.get("cleaner_name", "").strip()
            report.mechanical_technician = request.POST.get("mechanical_technician", "").strip()
            report.electrical_technician = request.POST.get("electrical_technician", "").strip()
            report.maintenance_manager = request.POST.get("maintenance_manager", "").strip()
            report.updated_at = timezone.now()
            report.save()
        messages.success(request, "تم حفظ تعديلات التقرير بنجاح.")
        return redirect("dashboard:report_detail", pk=report.pk)
    sections = {}
    for answer in report.answers.all(): sections.setdefault(answer.checklist_item.section.name, []).append(answer)
    return render(request, "dashboard/report_edit.html", {"report": report, "sections": sections.items()})
@login_required
@admin_required
def user_list(request):
    users = User.objects.select_related("factory").order_by("role", "name")
    return render(request, "dashboard/users.html", {"users": users})

@login_required
@admin_required
def user_form(request, pk=None):
    obj = get_object_or_404(User, pk=pk) if pk else None
    form = SupervisorForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f"تم حفظ بيانات المستخدم ({user.display_name}) بنجاح.")
        return redirect("dashboard:users")
    return render(request, "dashboard/form.html", {"form": form, "title": "تعديل مستخدم / مشرف" if obj else "إضافة مستخدم أو مشرف جديد"})

@login_required
@admin_required
def factories(request): return render(request, "dashboard/factories.html", {"factories": Factory.objects.prefetch_related("assets", "users")})
@login_required
@admin_required
def daily(request):
    today = timezone.localdate(); rows=[]; is_maintenance_day = MaintenanceCycleService.is_maintenance_day(today)
    for f in Factory.objects.filter(is_active=True):
        asset, state = MaintenanceCycleService.current_asset(f, today); report=MaintenanceReport.objects.filter(factory=f, report_date=today).select_related("asset", "supervisor").first(); rows.append({"factory":f,"asset":report.asset if report else asset,"report":report,"assets":MaintenanceCycleService.active_assets(f),"manual":bool(state.manual_selected_by_id)})
    return render(request,"dashboard/daily.html",{"rows":rows,"is_maintenance_day":is_maintenance_day})

@login_required
@admin_required
def select_daily_asset(request, factory_id):
    if request.method != "POST": return redirect("dashboard:daily")
    factory = get_object_or_404(Factory, pk=factory_id, is_active=True)
    asset = get_object_or_404(Asset, pk=request.POST.get("asset_id"), factory=factory)
    try:
        MaintenanceCycleService.select_current_asset(factory, asset, request.user)
        messages.success(request, f"تم تعيين الماكينة {asset.asset_code} لمهمة {factory.name} اليوم.")
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        if isinstance(detail, list): detail = str(detail[0])
        messages.error(request, detail)
    return redirect("dashboard:daily")
@login_required
def account(request):
    if request.method == "POST":
        form = AccountUpdateForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "تم حفظ وتحديث اسم المستخدم بنجاح.")
            return redirect("dashboard:account")
    else:
        form = AccountUpdateForm(instance=request.user)
    return render(request, "dashboard/account.html", {"form": form})

from maintenance.models import ChecklistTemplate
from dashboard.forms import ChecklistTemplateForm

@login_required
@admin_required
def checklist_list(request):
    checklists = ChecklistTemplate.objects.prefetch_related("sections__items").annotate(item_count=Count("sections__items", distinct=True))
    return render(request, "dashboard/checklists.html", {"checklists": checklists})

@login_required
@admin_required
def checklist_form(request, pk=None):
    obj = get_object_or_404(ChecklistTemplate, pk=pk) if pk else None
    form = ChecklistTemplateForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم حفظ قائمة الصيانة الدورية بنجاح.")
        return redirect("dashboard:checklists")
    return render(request, "dashboard/form.html", {"form": form, "title": "تعديل قائمة صيانة دورية" if obj else "إضافة قائمة صيانة دورية"})

import json
from django.db import transaction
from maintenance.models import ChecklistSection, ChecklistItem

@login_required
@admin_required
def checklist_builder(request, pk):
    tpl = get_object_or_404(ChecklistTemplate, pk=pk)
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            with transaction.atomic():
                existing_sections = {s.id: s for s in tpl.sections.all()}
                incoming_section_ids = [s.get('id') for s in data if s.get('id')]
                
                for sid in existing_sections:
                    if sid not in incoming_section_ids:
                        existing_sections[sid].delete()
                        
                for s_idx, sec_data in enumerate(data, 1):
                    sec_id = sec_data.get("id")
                    if sec_id and sec_id in existing_sections:
                        sec = existing_sections[sec_id]
                        sec.name = sec_data.get("name", "")
                        sec.sequence_order = s_idx
                        sec.save()
                    else:
                        sec = ChecklistSection.objects.create(template=tpl, name=sec_data.get("name", ""), sequence_order=s_idx)
                        
                    existing_items = {i.id: i for i in sec.items.all()}
                    incoming_items = sec_data.get("items", [])
                    incoming_item_ids = [i.get('id') for i in incoming_items if i.get('id')]
                    
                    for iid in existing_items:
                        if iid not in incoming_item_ids:
                            existing_items[iid].delete()
                            
                    for i_idx, item_data in enumerate(incoming_items, 1):
                        item_id = item_data.get("id")
                        if item_id and item_id in existing_items:
                            item = existing_items[item_id]
                            item.text = item_data.get("text", "")
                            item.sequence_order = i_idx
                            item.save()
                        else:
                            ChecklistItem.objects.create(section=sec, text=item_data.get("text", ""), sequence_order=i_idx)
            return JsonResponse({"message": "تم الحفظ بنجاح"})
        except Exception as e:
            return JsonResponse({"detail": str(e)}, status=400)
            
    data = []
    for sec in tpl.sections.prefetch_related("items").all():
        data.append({
            "id": sec.id,
            "name": sec.name,
            "items": [{"id": it.id, "text": it.text} for it in sec.items.all()]
        })
    return render(request, "dashboard/checklist_builder.html", {"template": tpl, "sections_json": json.dumps(data, ensure_ascii=False)})


import csv
from datetime import date
from django.http import HttpResponse

def _get_period_dates(period, date_from_str, date_to_str):
    today = timezone.localdate()
    if period == "last_month":
        first_of_this_month = today.replace(day=1)
        last_of_prev_month = first_of_this_month - timedelta(days=1)
        date_from = last_of_prev_month.replace(day=1)
        date_to = last_of_prev_month
    elif period == "last_30_days":
        date_from = today - timedelta(days=30)
        date_to = today
    elif period == "custom" and date_from_str and date_to_str:
        try:
            date_from = date.fromisoformat(date_from_str)
            date_to = date.fromisoformat(date_to_str)
            if date_from > date_to:
                date_from, date_to = date_to, date_from
        except (ValueError, TypeError):
            date_from = today.replace(day=1)
            date_to = today
    else:
        period = "current_month"
        date_from = today.replace(day=1)
        date_to = today
    return period, date_from, date_to

def _get_report_dataset(request):
    period_param = request.GET.get("period", "current_month")
    date_from_str = request.GET.get("date_from")
    date_to_str = request.GET.get("date_to")
    period, date_from, date_to = _get_period_dates(period_param, date_from_str, date_to_str)

    factory_id = request.GET.get("factory")
    asset_type = request.GET.get("asset_type")
    asset_code = request.GET.get("asset_code")

    reports_qs = MaintenanceReport.objects.filter(
        report_date__gte=date_from,
        report_date__lte=date_to
    ).select_related("factory", "asset", "supervisor").prefetch_related(
        "answers__checklist_item",
        "emergency_items__asset"
    ).order_by("-report_date", "-created_at")

    if factory_id:
        reports_qs = reports_qs.filter(factory_id=factory_id)
    if asset_type:
        reports_qs = reports_qs.filter(asset__asset_type=asset_type)
    if asset_code:
        reports_qs = reports_qs.filter(asset__asset_code__icontains=asset_code.strip())

    return period, date_from, date_to, factory_id, asset_type, asset_code, reports_qs

@login_required
@admin_required
def monthly_report(request):
    period, date_from, date_to, factory_id, asset_type, asset_code, reports_qs = _get_report_dataset(request)

    # Calculate targeted workdays (excluding Fridays)
    curr = date_from
    workdays_count = 0
    while curr <= date_to:
        if MaintenanceCycleService.is_maintenance_day(curr):
            workdays_count += 1
        curr += timedelta(days=1)

    if factory_id:
        factories_count = 1
        active_assets_qs = Asset.objects.filter(factory_id=factory_id, is_active=True, is_archived=False)
    else:
        active_factories = Factory.objects.filter(is_active=True)
        factories_count = active_factories.count()
        active_assets_qs = Asset.objects.filter(factory__in=active_factories, is_active=True, is_archived=False)

    if asset_type:
        active_assets_qs = active_assets_qs.filter(asset_type=asset_type)

    expected_reports_count = workdays_count * factories_count

    reports_list = list(reports_qs)
    total_reports = len(reports_list)

    compliance_rate = round((total_reports / expected_reports_count * 100), 1) if expected_reports_count > 0 else 100.0

    total_answers_evaluated = 0
    total_answers_checked = 0
    total_emergency_cases = 0

    machine_stats_map = {}
    emergency_incidents = []

    cleaner_counts = {}
    mechanical_counts = {}
    electrical_counts = {}
    manager_counts = {}
    supervisor_counts = {}

    for report in reports_list:
        answers = report.answers.all()
        rep_checked = sum(1 for a in answers if a.checked)
        rep_total = len(answers)
        total_answers_checked += rep_checked
        total_answers_evaluated += rep_total

        report.checked_count = rep_checked
        report.total_count = rep_total
        report.unchecked_count = rep_total - rep_checked
        report.compliance_pct = round((rep_checked / rep_total * 100), 1) if rep_total > 0 else 0

        emergencies = list(report.emergency_items.all())
        report.emergency_count = len(emergencies)
        total_emergency_cases += len(emergencies)
        for em in emergencies:
            emergency_incidents.append({
                "report": report,
                "asset": em.asset,
                "issue_description": em.issue_description,
                "responsible_person": em.responsible_person,
                "notes": em.notes,
                "date": report.report_date
            })

        aid = report.asset_id
        if aid not in machine_stats_map:
            machine_stats_map[aid] = {
                "asset": report.asset,
                "factory": report.factory,
                "reports_count": 0,
                "checked_count": 0,
                "total_items": 0,
                "emergencies": 0,
                "last_date": report.report_date
            }
        entry = machine_stats_map[aid]
        entry["reports_count"] += 1
        entry["checked_count"] += rep_checked
        entry["total_items"] += rep_total
        entry["emergencies"] += len(emergencies)
        if entry["last_date"] is None or report.report_date > entry["last_date"]:
            entry["last_date"] = report.report_date

        if report.supervisor:
            supervisor_counts[report.supervisor.display_name] = supervisor_counts.get(report.supervisor.display_name, 0) + 1
        if report.cleaner_name.strip():
            cleaner_counts[report.cleaner_name.strip()] = cleaner_counts.get(report.cleaner_name.strip(), 0) + 1
        if report.mechanical_technician.strip():
            mechanical_counts[report.mechanical_technician.strip()] = mechanical_counts.get(report.mechanical_technician.strip(), 0) + 1
        if report.electrical_technician.strip():
            electrical_counts[report.electrical_technician.strip()] = electrical_counts.get(report.electrical_technician.strip(), 0) + 1
        if report.maintenance_manager.strip():
            manager_counts[report.maintenance_manager.strip()] = manager_counts.get(report.maintenance_manager.strip(), 0) + 1

    overall_checklist_pct = round((total_answers_checked / total_answers_evaluated * 100), 1) if total_answers_evaluated > 0 else 0

    machines_summary = []
    for aid, st in machine_stats_map.items():
        st["health_pct"] = round((st["checked_count"] / st["total_items"] * 100), 1) if st["total_items"] > 0 else 0
        machines_summary.append(st)
    machines_summary.sort(key=lambda x: (x["factory"].name, -x["reports_count"], x["asset"].asset_code))

    serviced_assets_count = len(machine_stats_map)
    total_active_assets = active_assets_qs.count()

    # Pass query params forward for pagination and export links
    query_params = request.GET.copy()

    context = {
        "period": period,
        "date_from": date_from,
        "date_to": date_to,
        "workdays_count": workdays_count,
        "expected_reports_count": expected_reports_count,
        "total_reports": total_reports,
        "compliance_rate": compliance_rate,
        "total_answers_checked": total_answers_checked,
        "total_answers_evaluated": total_answers_evaluated,
        "overall_checklist_pct": overall_checklist_pct,
        "total_emergency_cases": total_emergency_cases,
        "emergency_incidents": emergency_incidents,
        "machines_summary": machines_summary,
        "serviced_assets_count": serviced_assets_count,
        "total_active_assets": total_active_assets,
        "reports": reports_list,
        "factories": Factory.objects.all(),
        "types": Asset.Type.choices,
        "selected_factory": factory_id,
        "selected_type": asset_type,
        "asset_code_query": asset_code or "",
        "cleaner_counts": sorted(cleaner_counts.items(), key=lambda x: -x[1]),
        "mechanical_counts": sorted(mechanical_counts.items(), key=lambda x: -x[1]),
        "electrical_counts": sorted(electrical_counts.items(), key=lambda x: -x[1]),
        "manager_counts": sorted(manager_counts.items(), key=lambda x: -x[1]),
        "supervisor_counts": sorted(supervisor_counts.items(), key=lambda x: -x[1]),
        "query_string": query_params.urlencode(),
        "generated_at": timezone.now(),
    }
    return render(request, "dashboard/monthly_report.html", context)

@login_required
@admin_required
def export_monthly_report_csv(request):
    period, date_from, date_to, factory_id, asset_type, asset_code, reports_qs = _get_report_dataset(request)

    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    filename = f"maintenance_report_{date_from}_to_{date_to}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    # UTF-8 BOM
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow([
        "تاريخ التقرير",
        "المصنع",
        "مهمة الصيانة الدورية",
        "كود الماكينة",
        "نوع الماكينة",
        "المشرف",
        "وقت البدء",
        "وقت الانتهاء",
        "بنود صيانة سليمة",
        "إجمالي بنود الصيانة",
        "نسبة سلامة الصيانة %",
        "عدد الأعطال الطارئة",
        "القائم بالنظافة",
        "فني الصيانة الميكانيكية",
        "فني الصيانة الكهربية",
        "مدير الصيانة",
        "الأعطال الطارئة المسجلة"
    ])

    for r in reports_qs:
        answers = r.answers.all()
        checked = sum(1 for a in answers if a.checked)
        total = len(answers)
        pct = f"{round(checked / total * 100, 1)}%" if total else "0%"
        em_list = [f"[{em.asset.asset_code}: {em.issue_description} - {em.responsible_person}]" for em in r.emergency_items.all()]
        em_text = " | ".join(em_list) if em_list else "لا يوجد"

        writer.writerow([
            r.report_date,
            r.factory.name,
            r.asset.maintenance_title,
            r.asset.asset_code,
            r.asset.get_asset_type_display(),
            r.supervisor.display_name,
            timezone.localtime(r.started_at_device).strftime("%H:%M") if r.started_at_device else "",
            timezone.localtime(r.completed_at_device).strftime("%H:%M") if r.completed_at_device else "",
            checked,
            total,
            pct,
            r.emergency_items.count(),
            r.cleaner_name or "-",
            r.mechanical_technician or "-",
            r.electrical_technician or "-",
            r.maintenance_manager or "-",
            em_text
        ])
    return response
