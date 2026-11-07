import hashlib
import io
import struct
import tempfile
import uuid
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from accounts.models import User
from factories.models import Factory
from .apk import inspect_apk
from .models import AppDevice, AppRelease


def apk_fixture(code=6, package="com.elwsam.operations", utf8=True):
    strings = ["manifest", "package", package, "versionCode", "versionName", "1.2.0", "uses-sdk", "minSdkVersion"]
    payload, offsets = bytearray(), []
    for value in strings:
        offsets.append(len(payload))
        encoded = value.encode("utf-8" if utf8 else "utf-16-le")
        payload.extend((bytes([len(value), len(encoded)]) if utf8 else struct.pack("<H", len(value))) + encoded + (b"\0" if utf8 else b"\0\0"))
    while len(payload) % 4:
        payload.append(0)
    pool = struct.pack("<HHIIIIII", 1, 28, 28 + len(offsets) * 4 + len(payload), len(strings), 0, 0x100 if utf8 else 0, 28 + len(offsets) * 4, 0)
    pool += struct.pack("<" + "I" * len(offsets), *offsets) + payload

    def element(name, attributes):
        attrs = b"".join(struct.pack("<IIIHBBI", 0xffffffff, key, value if kind == 3 else 0xffffffff, 8, 0, kind, value) for key, kind, value in attributes)
        return struct.pack("<HHIII", 0x102, 16, 36 + len(attrs), 0, 0xffffffff) + struct.pack("<IIHHHHHH", 0xffffffff, name, 20, 20, len(attributes), 0, 0, 0) + attrs

    body = pool + element(0, [(1, 3, 2), (3, 0x10, code), (4, 3, 5)]) + element(6, [(7, 0x10, 23)])
    manifest = struct.pack("<HHI", 3, 8, len(body) + 8) + body
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("AndroidManifest.xml", manifest)
        archive.writestr("classes.dex", b"fixture-not-installable")
    return SimpleUploadedFile("operations.apk", output.getvalue(), content_type="application/vnd.android.package-archive")


class UpdateTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        override = override_settings(MEDIA_ROOT=self.directory.name)
        override.enable()
        self.addCleanup(override.disable)
        self.factory = Factory.objects.get(code="F1")
        self.admin = User.objects.create_superuser("updates-admin", "pass")
        self.user = User.objects.create_user("updates-user", "pass", factory=self.factory)
        self.other = User.objects.create_user("updates-other", "pass", factory=Factory.objects.get(code="F2"))
        self.api = APIClient()
        self.device_id, self.secret = str(uuid.uuid4()), "a" * 64

    def info(self, version=5):
        return {"version_code": version, "version_name": "1.1.0", "android_sdk": 34, "label": "Factory phone"}

    def register(self, user=None, secret=None):
        self.api.credentials()
        self.api.force_authenticate(user or self.user)
        result = self.api.post(reverse("updates:register"), {**self.info(), "device_id": self.device_id, "device_secret": secret or self.secret}, format="json")
        self.api.force_authenticate(None)
        self.api.credentials(HTTP_X_DEVICE_ID=self.device_id, HTTP_X_DEVICE_TOKEN=self.secret)
        return result

    def upload(self, code=6, published=True):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("dashboard:app-updates"), {"apk": apk_fixture(code), "notes": "New feature", "publish_now": "on" if published else ""})
        self.assertEqual(response.status_code, 302)
        return AppRelease.objects.get(version_code=code)

    def test_reads_actual_version_for_utf8_and_utf16_manifests(self):
        for utf8 in (True, False):
            metadata = inspect_apk(apk_fixture(7, utf8=utf8))
            self.assertEqual((metadata["version_code"], metadata["version_name"], metadata["min_sdk"]), (7, "1.2.0", 23))
            self.assertEqual(len(metadata["sha256"]), 64)

    def test_only_admin_can_upload_or_view_device_inventory(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("dashboard:app-updates")).status_code, 302)
        self.assertEqual(self.client.post(reverse("dashboard:app-updates"), {"apk": apk_fixture()}).status_code, 302)
        self.assertFalse(AppRelease.objects.exists())

    def test_wrong_package_bad_archive_and_older_build_are_rejected(self):
        self.upload()
        for file in (apk_fixture(7, "wrong.package"), SimpleUploadedFile("bad.apk", b"not a zip"), apk_fixture(5), apk_fixture(6)):
            response = self.client.post(reverse("dashboard:app-updates"), {"apk": file})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["form"].errors)
        self.assertEqual(AppRelease.objects.count(), 1)

    def test_registration_requires_login_and_device_secret_cannot_be_replaced(self):
        self.assertEqual(self.api.post(reverse("updates:register"), {}, format="json").status_code, 401)
        self.assertEqual(self.register().status_code, 200)
        self.assertEqual(self.register(self.other, "b" * 64).status_code, 403)
        self.assertEqual(AppDevice.objects.get().last_user_id, self.user.pk)
        self.assertEqual(self.register(self.other).status_code, 200)
        device = AppDevice.objects.get()
        self.assertEqual(device.last_user_id, self.other.pk)
        self.assertEqual(device.factory_id, self.other.factory_id)

    def test_published_release_is_offered_and_download_is_authenticated(self):
        release = self.upload()
        self.register()
        latest = self.api.get(reverse("updates:latest"))
        self.assertEqual(latest.data["release"]["version_code"], 6)
        self.assertEqual(latest.data["release"]["size_bytes"], release.size_bytes)
        download = self.api.get(latest.data["release"]["download_path"])
        self.assertEqual(download.status_code, 200)
        body = b"".join(download.streaming_content)
        self.assertEqual(hashlib.sha256(body).hexdigest(), release.sha256)
        for headers in ({}, {"HTTP_X_DEVICE_ID": "malformed", "HTTP_X_DEVICE_TOKEN": self.secret}, {"HTTP_X_DEVICE_ID": self.device_id, "HTTP_X_DEVICE_TOKEN": "b" * 64}):
            self.api.credentials(**headers)
            self.assertEqual(self.api.get(reverse("updates:download", args=[release.pk])).status_code, 401)

    def test_draft_and_withdrawn_releases_are_not_distributed(self):
        release = self.upload(published=False)
        self.register()
        self.assertIsNone(self.api.get(reverse("updates:latest")).data["release"])
        self.assertEqual(self.api.get(reverse("updates:download", args=[release.pk])).status_code, 404)
        release.is_published = True
        release.save()
        self.assertIsNotNone(self.api.get(reverse("updates:latest")).data["release"])
        self.client.post(reverse("dashboard:app-updates"), {"action": "withdraw", "release_id": release.pk})
        self.assertIsNone(self.api.get(reverse("updates:latest")).data["release"])

    def test_inventory_confirms_installed_version_not_just_download_or_install_status(self):
        release = self.upload()
        self.register()
        for stage in ("downloading", "installing"):
            result = self.api.post(reverse("updates:heartbeat"), {**self.info(), "status": stage, "progress": 100, "release_id": release.pk}, format="json")
            self.assertEqual(result.status_code, 200)
            page = self.client.get(reverse("dashboard:app-updates"))
            self.assertEqual(page.context["current_count"], 0)
            self.assertEqual(page.context["pending_count"], 1)
        self.api.post(reverse("updates:heartbeat"), {**self.info(version=6), "status": "current"}, format="json")
        page = self.client.get(reverse("dashboard:app-updates"))
        self.assertEqual((page.context["current_count"], page.context["pending_count"]), (1, 0))
        self.assertIsNone(self.api.get(reverse("updates:latest")).data["release"])

    def test_revoked_device_cannot_poll_or_reregister(self):
        self.register()
        self.client.force_login(self.admin)
        self.client.post(reverse("dashboard:app-updates"), {"action": "revoke", "device_id": self.device_id})
        self.assertEqual(self.api.get(reverse("updates:latest")).status_code, 401)
        self.assertEqual(self.register().status_code, 403)

    def test_heartbeat_validation_and_failed_install_remain_pending(self):
        release = self.upload()
        self.register()
        result = self.api.post(reverse("updates:heartbeat"), {**self.info(), "status": "failed", "error": "signature mismatch", "release_id": release.pk}, format="json")
        self.assertEqual(result.status_code, 200)
        page = self.client.get(reverse("dashboard:app-updates"))
        self.assertContains(page, "signature mismatch")
        self.assertEqual(page.context["pending_count"], 1)
        for extra in ({"status": "invented"}, {"status": "downloading", "progress": 101}, {"status": "ready", "release_id": 9999}):
            self.assertEqual(self.api.post(reverse("updates:heartbeat"), {**self.info(), **extra}, format="json").status_code, 400)
