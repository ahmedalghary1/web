from datetime import timedelta
import uuid
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .forms import ReleaseForm
from .models import AppDevice, AppRelease

admin_required = user_passes_test(lambda user: user.is_authenticated and user.is_admin)


def device_update_action(request):
    action = request.POST.get("action")
    if action not in {"enable-updates", "disable-updates", "revoke"}:
        return False
    try:
        device_id = uuid.UUID(request.POST.get("device_id", ""))
    except (ValueError, TypeError, AttributeError):
        raise Http404
    device = get_object_or_404(AppDevice, pk=device_id)
    device.updates_enabled = action == "enable-updates"
    if device.updates_enabled:
        # Restore devices stopped using the previous irreversible control.
        device.is_active = True
    device.save(update_fields=["updates_enabled", "is_active"])
    messages.success(request, "تم تفعيل التحديثات للجهاز. سيستأنف الفحص عند اتصاله." if device.updates_enabled
                     else "تم إيقاف تحديثات الجهاز. يظل تسجيل الدخول ومتابعة نشاطه متاحين.")
    return True


def describe_device(device, now=None):
    now = now or timezone.now()
    device.presence_fresh = bool(device.presence_seen_at and device.presence_seen_at >= now - timedelta(seconds=90))
    device.open_now = bool(device.presence_fresh and device.is_foreground)
    device.presence_label = ("مفتوح الآن" if device.open_now else "في الخلفية" if device.presence_fresh
                             else "حالة الفتح غير معروفة" if device.presence_seen_at is None else "لا يوجد تأكيد نشاط حديث")
    device.screen_label = {"main": "الشاشة الرئيسية", "login": "تسجيل الدخول", "maintenance": "الصيانة",
                           "production": "الإنتاج والأعطال", "update": "تحديث التطبيق", "background": "في الخلفية"}.get(device.current_screen, "غير معروف")
    return device


def inventory():
    return AppDevice.objects.select_related("last_user__factory", "current_user__factory", "factory", "target_release")


@login_required
@admin_required
def devices(request):
    if request.method == "POST":
        device_update_action(request)
        return redirect(request.get_full_path())
    queryset = inventory()
    query = request.GET.get("q", "").strip()[:150]
    if query:
        queryset = queryset.filter(Q(label__icontains=query) | Q(model__icontains=query) |
                                   Q(current_user__name__icontains=query) | Q(current_user__phone__icontains=query) |
                                   Q(last_user__name__icontains=query) | Q(last_user__phone__icontains=query))
    now = timezone.now()
    records = [describe_device(device, now) for device in queryset]
    open_count = sum(device.open_now for device in records)
    state = request.GET.get("state", "")
    filtered = [device for device in records if state != "open" or device.open_now]
    return render(request, "dashboard/devices.html", {"devices": filtered, "total_count": len(records),
                  "open_count": open_count, "q": query, "state": state})


@login_required
@admin_required
def device_detail(request, pk):
    device = get_object_or_404(inventory(), pk=pk)
    if request.method == "POST":
        # Bind the control to this detail URL, not a different submitted ID.
        if request.POST.get("device_id") != str(device.pk):
            raise Http404
        device_update_action(request)
        return redirect("dashboard:device-detail", pk=device.pk)
    return render(request, "dashboard/device_detail.html", {"device": describe_device(device)})


@login_required
@admin_required
def releases(request):
    form = ReleaseForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        action = request.POST.get("action", "upload")
        if action in {"publish", "withdraw"}:
            release = get_object_or_404(AppRelease, pk=request.POST.get("release_id"))
            if action == "publish" and AppRelease.objects.filter(is_published=True, version_code__gt=release.version_code).exists():
                messages.error(request, "لا يمكن نشر إصدار أقدم من الإصدار الحالي.")
            else:
                release.is_published = action == "publish"
                if release.is_published:
                    release.published_at = timezone.now()
                release.save(update_fields=["is_published", "published_at"])
                messages.success(request, "تم نشر النسخة للأجهزة." if release.is_published else "تم إيقاف توزيع النسخة. لن يتم تخفيض إصدار أي جهاز.")
            return redirect("dashboard:app-updates")
        elif device_update_action(request):
            return redirect("dashboard:app-updates")
        elif action == "upload" and form.is_valid():
            release = AppRelease(**form.metadata, apk=form.cleaned_data["apk"], notes=form.cleaned_data["notes"],
                                 created_by=request.user, is_published=form.cleaned_data["publish_now"],
                                 published_at=timezone.now() if form.cleaned_data["publish_now"] else None)
            try:
                with transaction.atomic():
                    release.save()
            except IntegrityError:
                if release.apk.name:
                    release.apk.delete(save=False)
                form.add_error("apk", "تم رفع رقم البناء نفسه بالفعل. ارفع بناءً أحدث.")
            else:
                messages.success(request, f"تم رفع النسخة {release.version_name}، رقم البناء {release.version_code}.")
                return redirect("dashboard:app-updates")

    latest = AppRelease.latest()
    devices = inventory().all()
    cutoff = timezone.now() - timedelta(minutes=15)
    current_count = pending_count = 0
    for device in devices:
        device.is_current = bool(latest and device.version_code >= latest.version_code)
        device.recently_seen = device.last_seen >= cutoff
        if device.is_active and device.updates_enabled:
            current_count += device.is_current
            pending_count += bool(latest and not device.is_current)
    return render(request, "dashboard/app_updates.html", {
        "form": form, "releases": AppRelease.objects.select_related("created_by").all(),
        "devices": devices, "latest": latest, "current_count": current_count, "pending_count": pending_count,
    })
