import uuid
from django.conf import settings
from django.db import models


def apk_path(instance, filename):
    return f"app-releases/{uuid.uuid4().hex}.apk"


class AppRelease(models.Model):
    version_code = models.PositiveIntegerField(unique=True)
    version_name = models.CharField(max_length=100)
    min_sdk = models.PositiveIntegerField()
    apk = models.FileField(upload_to=apk_path)
    sha256 = models.CharField(max_length=64)
    size_bytes = models.PositiveBigIntegerField()
    notes = models.TextField(blank=True)
    is_published = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-version_code"]

    @classmethod
    def latest(cls):
        return cls.objects.filter(is_published=True).first()


class AppDevice(models.Model):
    class Status(models.TextChoices):
        CURRENT = "current", "يعمل بالإصدار المثبّت"
        DOWNLOADING = "downloading", "جارٍ تنزيل التحديث"
        READY = "ready", "التحديث جاهز للتثبيت"
        PERMISSION = "permission", "ينتظر سماح Android بالتثبيت"
        CONFIRMATION = "confirmation", "ينتظر تأكيد التثبيت من Android"
        INSTALLING = "installing", "جارٍ التثبيت"
        FAILED = "failed", "تعذر التحديث"
        INCOMPATIBLE = "incompatible", "إصدار Android غير متوافق"

    id = models.UUIDField(primary_key=True, editable=False)
    secret_hash = models.CharField(max_length=64)
    label = models.CharField(max_length=150)
    android_sdk = models.PositiveIntegerField()
    version_code = models.PositiveIntegerField()
    version_name = models.CharField(max_length=100)
    last_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    factory = models.ForeignKey("factories.Factory", null=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CURRENT)
    target_release = models.ForeignKey(AppRelease, null=True, blank=True, on_delete=models.SET_NULL)
    progress = models.PositiveSmallIntegerField(default=0)
    error = models.CharField(max_length=1000, blank=True)
    is_active = models.BooleanField(default=True)
    last_seen = models.DateTimeField()
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-last_seen"]
