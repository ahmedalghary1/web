from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .forms import ReleaseForm
from .models import AppDevice, AppRelease

admin_required = user_passes_test(lambda user: user.is_authenticated and user.is_admin)


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
        elif action == "revoke":
            device = get_object_or_404(AppDevice, pk=request.POST.get("device_id"))
            device.is_active = False
            device.save(update_fields=["is_active"])
            messages.success(request, "تم إيقاف وصول الجهاز لخدمة التحديثات.")
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
    devices = AppDevice.objects.select_related("last_user", "factory", "target_release").all()
    cutoff = timezone.now() - timedelta(minutes=15)
    current_count = pending_count = 0
    for device in devices:
        device.is_current = bool(latest and device.version_code >= latest.version_code)
        device.recently_seen = device.last_seen >= cutoff
        if device.is_active:
            current_count += device.is_current
            pending_count += bool(latest and not device.is_current)
    return render(request, "dashboard/app_updates.html", {
        "form": form, "releases": AppRelease.objects.select_related("created_by").all(),
        "devices": devices, "latest": latest, "current_count": current_count, "pending_count": pending_count,
    })
