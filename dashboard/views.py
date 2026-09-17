from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from accounts.models import User
from assets.models import Asset
from dashboard.forms import AssetForm, SupervisorForm
from factories.models import Factory
from maintenance.models import MaintenanceReport, MaintenanceReportItem
from maintenance.services.cycle import MaintenanceCycleService

admin_required = user_passes_test(lambda u: u.is_authenticated and u.role == User.Role.ADMIN)
@login_required
@admin_required
def home(request):
    today = timezone.localdate(); cards = []; missed_count = 0
    for factory in Factory.objects.filter(is_active=True):
        asset, _ = MaintenanceCycleService.current_asset(factory, today); report = MaintenanceReport.objects.filter(factory=factory, report_date=today).select_related("asset", "supervisor").first(); cards.append({"factory": factory, "asset": report.asset if report else asset, "report": report})
        dates = set(MaintenanceReport.objects.filter(factory=factory, report_date__lt=today).values_list("report_date", flat=True))
        if dates: missed_count += max(0, (today - min(dates)).days - len(dates))
    reports = MaintenanceReport.objects.select_related("factory", "asset", "supervisor").prefetch_related("answers").all()[:8]
    notes = MaintenanceReportItem.objects.exclude(note="").select_related("report__factory", "report__asset", "checklist_item").order_by("-report__created_at")[:6]
    return render(request, "dashboard/home.html", {"cards": cards, "reports": reports, "notes": notes, "missed_count": missed_count, "completed_count": MaintenanceReport.objects.filter(report_date__gte=today-timedelta(days=30)).count()})
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
    obj = get_object_or_404(Asset, pk=pk, is_archived=False) if pk else None; form = AssetForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid(): form.save(); messages.success(request, "تم حفظ بيانات الماكينة بنجاح."); return redirect("dashboard:assets")
    return render(request, "dashboard/form.html", {"form": form, "title": "تعديل ماكينة" if obj else "إضافة ماكينة"})
@login_required
@admin_required
def asset_archive(request, pk):
    if request.method == "POST":
        asset = get_object_or_404(Asset, pk=pk); asset.is_archived = True; asset.is_active = False; asset.save(); messages.success(request, "تمت أرشفة الماكينة مع الحفاظ على سجلها التاريخي.")
    return redirect("dashboard:assets")
@login_required
@admin_required
def asset_reorder(request):
    if request.method != "POST": return JsonResponse({"detail": "طريقة الطلب غير مسموحة."}, status=405)
    try:
        ids = [int(v) for v in request.POST.getlist("ids[]")]; factory = Factory.objects.get(pk=request.POST["factory"]); MaintenanceCycleService.reorder(factory, ids); return JsonResponse({"message": "تم تحديث الترتيب."})
    except Exception as exc: return JsonResponse({"detail": str(exc)}, status=400)
@login_required
@admin_required
def report_list(request):
    qs = MaintenanceReport.objects.select_related("factory", "asset", "supervisor").annotate(checked_count=Count("answers", filter=Q(answers__checked=True)), unchecked_count=Count("answers", filter=Q(answers__checked=False)))
    for field, param in {"factory_id":"factory","asset__asset_type":"asset_type","supervisor_id":"supervisor","report_date":"date"}.items():
        if request.GET.get(param): qs = qs.filter(**{field: request.GET[param]})
    if request.GET.get("asset_code"): qs = qs.filter(asset__asset_code__icontains=request.GET["asset_code"])
    if request.GET.get("date_from"): qs = qs.filter(report_date__gte=request.GET["date_from"])
    if request.GET.get("date_to"): qs = qs.filter(report_date__lte=request.GET["date_to"])
    reports = Paginator(qs, 25).get_page(request.GET.get("page"))
    return render(request, "dashboard/reports.html", {"reports": reports, "factories": Factory.objects.all(), "supervisors": User.objects.filter(role=User.Role.MAINTENANCE_SUPERVISOR), "types": Asset.Type.choices})
@login_required
@admin_required
def report_detail(request, pk):
    report = get_object_or_404(MaintenanceReport.objects.select_related("factory", "asset", "supervisor").prefetch_related("answers__checklist_item__section"), pk=pk); sections = {}
    for answer in report.answers.all(): sections.setdefault(answer.checklist_item.section.name, []).append(answer)
    return render(request, "dashboard/report_detail.html", {"report": report, "sections": sections.items()})

@login_required
@admin_required
def report_edit(request, pk):
    report = get_object_or_404(MaintenanceReport.objects.select_related("factory", "asset", "supervisor").prefetch_related("answers__checklist_item__section"), pk=pk)
    if request.method == "POST":
        with transaction.atomic():
            for answer in report.answers.all():
                checked_str = request.POST.get(f"checked_{answer.id}")
                answer.checked = (checked_str == "on")
                answer.note = request.POST.get(f"note_{answer.id}", "")
                answer.save()
            report.updated_at = timezone.now()
            report.save()
        messages.success(request, "تم حفظ تعديلات التقرير بنجاح.")
        return redirect("dashboard:report_detail", pk=report.pk)
    sections = {}
    for answer in report.answers.all(): sections.setdefault(answer.checklist_item.section.name, []).append(answer)
    return render(request, "dashboard/report_edit.html", {"report": report, "sections": sections.items()})
@login_required
@admin_required
def user_list(request): return render(request, "dashboard/users.html", {"users": User.objects.filter(role=User.Role.MAINTENANCE_SUPERVISOR).select_related("factory")})
@login_required
@admin_required
def user_form(request, pk=None):
    obj = get_object_or_404(User, pk=pk, role=User.Role.MAINTENANCE_SUPERVISOR) if pk else None; form = SupervisorForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid(): form.save(); messages.success(request, "تم حفظ بيانات مشرف الصيانة."); return redirect("dashboard:users")
    return render(request, "dashboard/form.html", {"form": form, "title": "تعديل مشرف" if obj else "إضافة مشرف صيانة"})
@login_required
@admin_required
def factories(request): return render(request, "dashboard/factories.html", {"factories": Factory.objects.prefetch_related("assets", "users")})
@login_required
@admin_required
def daily(request):
    today = timezone.localdate(); rows=[]
    for f in Factory.objects.filter(is_active=True):
        asset, _ = MaintenanceCycleService.current_asset(f, today); report=MaintenanceReport.objects.filter(factory=f, report_date=today).select_related("asset", "supervisor").first(); rows.append({"factory":f,"asset":report.asset if report else asset,"report":report})
    return render(request,"dashboard/daily.html",{"rows":rows})
@login_required
def account(request): return render(request, "dashboard/account.html")

from maintenance.models import ChecklistTemplate
from dashboard.forms import ChecklistTemplateForm

@login_required
@admin_required
def checklist_list(request):
    return render(request, "dashboard/checklists.html", {"checklists": ChecklistTemplate.objects.prefetch_related("sections__items").all()})

@login_required
@admin_required
def checklist_form(request, pk=None):
    obj = get_object_or_404(ChecklistTemplate, pk=pk) if pk else None
    form = ChecklistTemplateForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم حفظ قائمة الفحص بنجاح.")
        return redirect("dashboard:checklists")
    return render(request, "dashboard/form.html", {"form": form, "title": "تعديل قائمة فحص" if obj else "إضافة قائمة فحص"})

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
