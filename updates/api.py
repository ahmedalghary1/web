import hashlib
import hmac
from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth.models import AnonymousUser
from django.http import FileResponse
from django.urls import reverse
from django.utils import timezone
from rest_framework import serializers
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, NotFound
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import SimpleRateThrottle
from drf_spectacular.utils import OpenApiTypes, extend_schema
from .models import AppDevice, AppRelease


def hash_secret(secret):
    return hashlib.sha256(secret.encode()).hexdigest()


class DeviceAuthentication(BaseAuthentication):
    def authenticate(self, request):
        device_id = request.headers.get("X-Device-ID")
        secret = request.headers.get("X-Device-Token", "")
        try:
            device = AppDevice.objects.select_related("last_user").get(pk=device_id, is_active=True)
        except (AppDevice.DoesNotExist, ValueError, TypeError, DjangoValidationError):
            raise AuthenticationFailed("الجهاز غير مسجل أو تم إيقافه.")
        if len(secret) != 64 or not hmac.compare_digest(device.secret_hash, hash_secret(secret)):
            raise AuthenticationFailed("بيانات الجهاز غير صحيحة.")
        return device.last_user or AnonymousUser(), device

    def authenticate_header(self, request):
        return "Device"


class IsDevice(BasePermission):
    def has_permission(self, request, view):
        return isinstance(request.auth, AppDevice)


class DeviceInfoSerializer(serializers.Serializer):
    version_code = serializers.IntegerField(min_value=1, max_value=2147483647)
    version_name = serializers.CharField(max_length=100)
    android_sdk = serializers.IntegerField(min_value=23, max_value=100)
    label = serializers.CharField(max_length=150)


class RegistrationSerializer(DeviceInfoSerializer):
    device_id = serializers.UUIDField()
    device_secret = serializers.RegexField(r"^[a-f0-9]{64}$")


class HeartbeatSerializer(DeviceInfoSerializer):
    status = serializers.ChoiceField(choices=AppDevice.Status.choices)
    progress = serializers.IntegerField(min_value=0, max_value=100, default=0)
    error = serializers.CharField(max_length=1000, allow_blank=True, default="")
    release_id = serializers.IntegerField(min_value=1, allow_null=True, required=False)


class RegisterView(APIView):
    permission_classes = [IsAuthenticated]
    @extend_schema(request=RegistrationSerializer, responses=OpenApiTypes.OBJECT)
    @transaction.atomic
    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        device_id, secret = values.pop("device_id"), values.pop("device_secret")
        device, created = AppDevice.objects.select_for_update().get_or_create(
            pk=device_id, defaults={**values, "secret_hash": hash_secret(secret), "last_seen": timezone.now()})
        if not created and (not device.is_active or not hmac.compare_digest(device.secret_hash, hash_secret(secret))):
            raise PermissionDenied("لا يمكن ربط بيانات هذا الجهاز.")
        for key, value in values.items():
            setattr(device, key, value)
        device.last_user, device.factory, device.last_seen = request.user, request.user.factory, timezone.now()
        device.save()
        return Response({"registered": True})


class DeviceThrottle(SimpleRateThrottle):
    scope = "device_updates"
    rate = "120/minute"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": str(request.auth.pk)}


class DeviceView(APIView):
    authentication_classes = [DeviceAuthentication]
    permission_classes = [IsDevice]
    throttle_classes = [DeviceThrottle]


class LatestView(DeviceView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        AppDevice.objects.filter(pk=request.auth.pk).update(last_seen=timezone.now())
        release = AppRelease.latest()
        if not release or release.version_code <= request.auth.version_code:
            return Response({"release": None})
        return Response({"release": {
            "id": release.pk, "version_code": release.version_code, "version_name": release.version_name,
            "min_sdk": release.min_sdk, "sha256": release.sha256, "size_bytes": release.size_bytes,
            "notes": release.notes, "download_path": reverse("updates:download", args=[release.pk]),
        }})


class HeartbeatView(DeviceView):
    @extend_schema(request=HeartbeatSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = HeartbeatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        release_id = values.pop("release_id", None)
        if release_id and not AppRelease.objects.filter(pk=release_id).exists():
            raise serializers.ValidationError({"release_id": "النسخة غير موجودة."})
        AppDevice.objects.filter(pk=request.auth.pk).update(**values, target_release_id=release_id, last_seen=timezone.now())
        return Response({"received": True})


class DownloadView(DeviceView):
    @extend_schema(responses=OpenApiTypes.BINARY)
    def get(self, request, pk):
        release = AppRelease.objects.filter(pk=pk, is_published=True).first()
        if not release:
            raise NotFound("النسخة غير منشورة.")
        try:
            response = FileResponse(release.apk.open("rb"), content_type="application/vnd.android.package-archive", as_attachment=True, filename=f"elwsam-{release.version_code}.apk")
        except FileNotFoundError:
            raise NotFound("ملف النسخة غير متاح.")
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Length"] = release.size_bytes
        return response
