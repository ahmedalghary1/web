from functools import wraps
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.core.paginator import Paginator

from assets.models import Asset
from factories.models import Factory
from .models import (
    Product,
    MachineOperator,
    MachineProductionDefault,
    ProductionShiftReport,
    MachineProductionEntry,
    ProductionStoppage,
)
from .forms import MachineProductionDefaultForm, ProductForm, MachineOperatorForm


def production_access_required(view_func):
    """Decorator ensuring user is authenticated and has permission to access production system."""
    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        if not getattr(request.user, "can_access_production", True):
            messages.error(request, "ليس لديك صلاحية الوصول إلى نظام الإنتاج والأعطال.")
            if getattr(request.user, "can_access_maintenance", False):
                return redirect("dashboard:home")
            return redirect("login")
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def get_active_factory_context(request):
    """
    Returns (active_factory, factories_list, is_admin)
    - Administrators (superuser or role ADMIN) are NOT bound to a single factory:
      They can switch between active factories or view 'all'.
      Switching can happen via ?factory=ID or ?factory=all, persisted in session.
    - Supervisors (PRODUCTION_SUPERVISOR or GENERAL_SUPERVISOR):
      Strictly restricted to request.user.factory.
    """
    user = request.user
    is_admin = getattr(user, "is_admin", user.is_superuser or user.role == "ADMIN")
    factories = list(Factory.objects.filter(is_active=True).order_by("id"))

    if not is_admin:
        factory = getattr(user, "factory", None)
        return factory, [factory] if factory else [], False

    selected_param = request.GET.get("factory")
    if selected_param:
        if selected_param == "all":
            request.session["production_factory_id"] = "all"
            return None, factories, True
        matched = next((f for f in factories if str(f.id) == str(selected_param)), None)
        if matched:
            request.session["production_factory_id"] = matched.id
            return matched, factories, True

    session_id = request.session.get("production_factory_id")
    if session_id == "all":
        return None, factories, True
    elif session_id:
        matched = next((f for f in factories if str(f.id) == str(session_id)), None)
        if matched:
            return matched, factories, True

    # Default to first active factory for admin
    default_factory = factories[0] if factories else None
    if default_factory:
        request.session["production_factory_id"] = default_factory.id
    return default_factory, factories, True


@production_access_required
def home(request):
    factory, factories, is_admin = get_active_factory_context(request)
    if not is_admin and not factory:
        messages.error(request, "حساب المشرف غير مربوط بمصنع، يرجى مراجعة إدارة النظام.")
        return redirect("dashboard:home")

    today = timezone.localdate()

    reports_qs = ProductionShiftReport.objects.all()
    entries_qs = MachineProductionEntry.objects.all()
    stoppages_qs = ProductionStoppage.objects.all()
    assets_qs = Asset.objects.filter(is_active=True, is_archived=False)

    if factory:
        reports_qs = reports_qs.filter(factory=factory)
        entries_qs = entries_qs.filter(report__factory=factory)
        stoppages_qs = stoppages_qs.filter(report__factory=factory)
        assets_qs = assets_qs.filter(factory=factory)

    today_reports = reports_qs.filter(report_date=today).select_related(
        "supervisor", "handover_to_supervisor", "factory"
    ).order_by("-created_at")

    today_entries = entries_qs.filter(report__report_date=today)
    total_weight_today = today_entries.aggregate(s=Sum("final_production_weight_kg"))["s"] or 0.0
    active_machines_count = today_entries.values("asset").distinct().count()
    total_machines = assets_qs.count()

    today_stoppages = stoppages_qs.filter(report__report_date=today)
    stoppages_count = today_stoppages.count()
    total_stoppage_mins = today_stoppages.aggregate(s=Sum("duration_minutes"))["s"] or 0

    today_product_changes = today_entries.filter(product_changed=True).count()
    today_operator_changes = today_entries.filter(operator_changed=True).count()

    pending_handovers = reports_qs.filter(
        status=ProductionShiftReport.Status.PENDING_HANDOVER
    ).select_related("supervisor", "factory").order_by("-created_at")[:5]

    recent_reports = reports_qs.select_related(
        "supervisor", "handover_to_supervisor", "factory"
    ).prefetch_related("machine_entries").order_by("-report_date", "-created_at")[:10]

    context = {
        "today": today,
        "factory": factory,
        "factories": factories,
        "is_admin": is_admin,
        "today_reports": today_reports,
        "total_weight_today": round(total_weight_today, 2),
        "active_machines_count": active_machines_count,
        "total_machines": total_machines,
        "stoppages_count": stoppages_count,
        "total_stoppage_mins": total_stoppage_mins,
        "today_product_changes": today_product_changes,
        "today_operator_changes": today_operator_changes,
        "pending_handovers": pending_handovers,
        "recent_reports": recent_reports,
    }
    return render(request, "production/home.html", context)


@production_access_required
def report_list(request):
    factory, factories, is_admin = get_active_factory_context(request)
    if not is_admin and not factory:
        messages.error(request, "حساب المشرف غير مربوط بمصنع.")
        return redirect("dashboard:home")

    reports = ProductionShiftReport.objects.select_related(
        "supervisor", "handover_to_supervisor", "factory"
    ).prefetch_related("machine_entries", "stoppages").order_by("-report_date", "-created_at")

    factory_filter = request.GET.get("factory")
    if not is_admin:
        reports = reports.filter(factory=factory)
    else:
        if factory_filter and factory_filter != "all":
            reports = reports.filter(factory_id=factory_filter)
        elif factory and not factory_filter:
            reports = reports.filter(factory=factory)

    date_filter = request.GET.get("date")
    shift_filter = request.GET.get("shift")
    status_filter = request.GET.get("status")

    if date_filter:
        reports = reports.filter(report_date=date_filter)
    if shift_filter:
        reports = reports.filter(shift=shift_filter)
    if status_filter:
        reports = reports.filter(status=status_filter)

    paginator = Paginator(reports, 15)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    context = {
        "page_obj": page_obj,
        "factory": factory,
        "factories": factories,
        "is_admin": is_admin,
        "selected_factory_id": factory_filter or (str(factory.id) if factory else "all"),
        "date_filter": date_filter,
        "shift_filter": shift_filter,
        "status_filter": status_filter,
    }
    return render(request, "production/report_list.html", context)


@production_access_required
def report_detail(request, pk):
    factory, _, is_admin = get_active_factory_context(request)
    qs = ProductionShiftReport.objects.select_related("supervisor", "handover_to_supervisor", "factory")
    if not is_admin:
        report = get_object_or_404(qs, pk=pk, factory=factory)
    else:
        report = get_object_or_404(qs, pk=pk)

    entries = report.machine_entries.select_related("asset", "operator", "original_operator", "product", "original_product").all()
    stoppages = report.stoppages.select_related("asset").all()

    total_weight = entries.aggregate(s=Sum("final_production_weight_kg"))["s"] or 0.0
    product_changes_count = entries.filter(product_changed=True).count()
    operator_changes_count = entries.filter(operator_changed=True).count()
    total_stoppage_mins = stoppages.aggregate(s=Sum("duration_minutes"))["s"] or 0

    context = {
        "report": report,
        "entries": entries,
        "stoppages": stoppages,
        "total_weight": round(total_weight, 2),
        "product_changes_count": product_changes_count,
        "operator_changes_count": operator_changes_count,
        "total_stoppage_mins": total_stoppage_mins,
        "is_admin": is_admin,
    }
    return render(request, "production/report_detail.html", context)


@production_access_required
def confirm_handover(request, pk):
    if request.method != "POST":
        return redirect("production:report_detail", pk=pk)

    factory, _, is_admin = get_active_factory_context(request)
    qs = ProductionShiftReport.objects.all()
    if not is_admin:
        report = get_object_or_404(qs, pk=pk, factory=factory)
    else:
        report = get_object_or_404(qs, pk=pk)

    report.status = ProductionShiftReport.Status.CONFIRMED
    report.handover_to_supervisor = request.user
    report.handover_confirmed_at = timezone.now()
    notes = request.POST.get("handover_notes", "").strip()
    if notes:
        report.handover_notes = notes
    report.save()

    messages.success(request, f"تم تأكيد استلام الوردية ({report.get_shift_display()}) بنجاح.")
    return redirect("production:report_detail", pk=pk)


@production_access_required
def machine_defaults(request):
    factory, factories, is_admin = get_active_factory_context(request)
    if not is_admin and not factory:
        messages.error(request, "المستخدم غير مربوط بمصنع.")
        return redirect("dashboard:home")

    if factory:
        assets = Asset.objects.filter(
            factory=factory, is_archived=False
        ).select_related(
            "production_default",
            "production_default__default_product",
            "production_default__default_operator",
            "factory",
        ).order_by("sequence_order", "id")
    else:
        assets = Asset.objects.filter(
            is_archived=False
        ).select_related(
            "production_default",
            "production_default__default_product",
            "production_default__default_operator",
            "factory",
        ).order_by("factory__id", "sequence_order", "id")

    context = {
        "assets": assets,
        "factory": factory,
        "factories": factories,
        "is_admin": is_admin,
    }
    return render(request, "production/machine_defaults.html", context)


@production_access_required
def machine_default_edit(request, asset_id):
    _, _, is_admin = get_active_factory_context(request)
    if not is_admin:
        asset = get_object_or_404(Asset, id=asset_id, factory=request.user.factory)
    else:
        asset = get_object_or_404(Asset, id=asset_id)

    default_obj, _ = MachineProductionDefault.objects.get_or_create(asset=asset)

    if request.method == "POST":
        form = MachineProductionDefaultForm(request.POST, instance=default_obj, factory=asset.factory)
        if form.is_valid():
            form.save()
            messages.success(request, f"تم تحديث إعدادات الإنتاج لماكينة {asset.asset_code} بنجاح.")
            return redirect("production:machine_defaults")
    else:
        form = MachineProductionDefaultForm(instance=default_obj, factory=asset.factory)

    context = {
        "asset": asset,
        "form": form,
        "is_admin": is_admin,
    }
    return render(request, "production/machine_default_edit.html", context)


@production_access_required
def product_list(request):
    factory, factories, is_admin = get_active_factory_context(request)
    if not is_admin:
        products = Product.objects.filter(factory=factory).order_by("name")
    else:
        if factory:
            products = Product.objects.filter(factory=factory).select_related("factory").order_by("name")
        else:
            products = Product.objects.all().select_related("factory").order_by("factory__name", "name")

    context = {
        "products": products,
        "factory": factory,
        "factories": factories,
        "is_admin": is_admin,
    }
    return render(request, "production/product_list.html", context)


@production_access_required
def product_form(request, pk=None):
    factory, factories, is_admin = get_active_factory_context(request)
    if not is_admin:
        instance = get_object_or_404(Product, pk=pk, factory=factory) if pk else None
    else:
        instance = get_object_or_404(Product, pk=pk) if pk else None

    if request.method == "POST":
        form = ProductForm(request.POST, instance=instance)
        if form.is_valid():
            prod = form.save(commit=False)
            if is_admin and request.POST.get("factory"):
                prod.factory_id = request.POST.get("factory")
            elif not prod.factory_id:
                prod.factory = factory or (factories[0] if factories else None)
            prod.save()
            messages.success(request, f"تم حفظ المنتج '{prod.name}' بنجاح.")
            return redirect("production:products")
    else:
        form = ProductForm(instance=instance)

    context = {
        "form": form,
        "instance": instance,
        "factory": factory,
        "factories": factories,
        "is_admin": is_admin,
    }
    return render(request, "production/product_form.html", context)


@production_access_required
def product_toggle(request, pk):
    _, _, is_admin = get_active_factory_context(request)
    if not is_admin:
        prod = get_object_or_404(Product, pk=pk, factory=request.user.factory)
    else:
        prod = get_object_or_404(Product, pk=pk)
    prod.is_active = not prod.is_active
    prod.save()
    status_label = "تفعيل" if prod.is_active else "تعطيل"
    messages.success(request, f"تم {status_label} المنتج '{prod.name}'.")
    return redirect("production:products")


@production_access_required
def operator_list(request):
    factory, factories, is_admin = get_active_factory_context(request)
    if not is_admin:
        operators = MachineOperator.objects.filter(factory=factory).order_by("name")
    else:
        if factory:
            operators = MachineOperator.objects.filter(factory=factory).select_related("factory").order_by("name")
        else:
            operators = MachineOperator.objects.all().select_related("factory").order_by("factory__name", "name")

    context = {
        "operators": operators,
        "factory": factory,
        "factories": factories,
        "is_admin": is_admin,
    }
    return render(request, "production/operator_list.html", context)


@production_access_required
def operator_form(request, pk=None):
    factory, factories, is_admin = get_active_factory_context(request)
    if not is_admin:
        instance = get_object_or_404(MachineOperator, pk=pk, factory=factory) if pk else None
    else:
        instance = get_object_or_404(MachineOperator, pk=pk) if pk else None

    if request.method == "POST":
        form = MachineOperatorForm(request.POST, instance=instance)
        if form.is_valid():
            op = form.save(commit=False)
            if is_admin and request.POST.get("factory"):
                op.factory_id = request.POST.get("factory")
            elif not op.factory_id:
                op.factory = factory or (factories[0] if factories else None)
            op.save()
            messages.success(request, f"تم حفظ العامل '{op.name}' بنجاح.")
            return redirect("production:operators")
    else:
        form = MachineOperatorForm(instance=instance)

    context = {
        "form": form,
        "instance": instance,
        "factory": factory,
        "factories": factories,
        "is_admin": is_admin,
    }
    return render(request, "production/operator_form.html", context)


@production_access_required
def operator_toggle(request, pk):
    _, _, is_admin = get_active_factory_context(request)
    if not is_admin:
        op = get_object_or_404(MachineOperator, pk=pk, factory=request.user.factory)
    else:
        op = get_object_or_404(MachineOperator, pk=pk)
    op.is_active = not op.is_active
    op.save()
    status_label = "تفعيل" if op.is_active else "تعطيل"
    messages.success(request, f"تم {status_label} العامل '{op.name}'.")
    return redirect("production:operators")


@production_access_required
def stoppage_list(request):
    factory, factories, is_admin = get_active_factory_context(request)
    stoppages = ProductionStoppage.objects.select_related(
        "report", "asset", "report__supervisor", "report__factory"
    ).order_by("-report__report_date", "-id")

    if not is_admin:
        stoppages = stoppages.filter(report__factory=factory)
    else:
        factory_filter = request.GET.get("factory")
        if factory_filter and factory_filter != "all":
            stoppages = stoppages.filter(report__factory_id=factory_filter)
        elif factory and not factory_filter:
            stoppages = stoppages.filter(report__factory=factory)

    stoppage_type = request.GET.get("type")
    date_filter = request.GET.get("date")
    if stoppage_type:
        stoppages = stoppages.filter(stoppage_type=stoppage_type)
    if date_filter:
        stoppages = stoppages.filter(report__report_date=date_filter)

    paginator = Paginator(stoppages, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    total_mins = stoppages.aggregate(s=Sum("duration_minutes"))["s"] or 0

    context = {
        "page_obj": page_obj,
        "stoppage_type": stoppage_type,
        "date_filter": date_filter,
        "total_mins": total_mins,
        "factory": factory,
        "factories": factories,
        "is_admin": is_admin,
        "selected_factory_id": request.GET.get("factory") or (str(factory.id) if factory else "all"),
    }
    return render(request, "production/stoppage_list.html", context)
