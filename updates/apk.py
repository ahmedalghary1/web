"""Read the APK's own binary manifest without executing or extracting the APK."""
import hashlib
import struct
import zipfile

from django.core.exceptions import ValidationError

PACKAGE = "com.elwsam.operations"
MAX_APK_BYTES = 200 * 1024 * 1024


def manifest_metadata(data):
    def u16(at):
        return struct.unpack_from("<H", data, at)[0]

    def u32(at):
        return struct.unpack_from("<I", data, at)[0]

    if len(data) < 8 or u16(0) != 3 or u32(4) != len(data):
        raise ValueError("Invalid binary manifest")
    strings, root, sdk = [], {}, {}
    offset = u16(2)
    while offset < len(data):
        kind, header, size = struct.unpack_from("<HHI", data, offset)
        if size < header or header < 8 or offset + size > len(data):
            raise ValueError("Invalid manifest chunk")
        if kind == 1:
            count, flags, start = u32(offset + 8), u32(offset + 16), u32(offset + 20)
            if count > 100000 or header + count * 4 > size:
                raise ValueError("Invalid string pool")
            utf8 = bool(flags & 0x100)

            def length(at):
                first = data[at] if utf8 else u16(at)
                step, mask = (1, 0x80) if utf8 else (2, 0x8000)
                if first & mask:
                    second = data[at + step] if utf8 else u16(at + step)
                    return ((first & (mask - 1)) << (7 if utf8 else 16)) | second, at + step * 2
                return first, at + step

            for index in range(count):
                at = offset + start + u32(offset + header + index * 4)
                chars, at = length(at)
                if utf8:
                    byte_count, at = length(at)
                else:
                    byte_count = chars * 2
                if at + byte_count > offset + size:
                    raise ValueError("Invalid manifest string")
                strings.append(data[at:at + byte_count].decode("utf-8" if utf8 else "utf-16-le"))
        elif kind == 0x102:
            element = strings[u32(offset + 20)]
            attributes = {}
            attr_size, count = u16(offset + 26), u16(offset + 28)
            first = offset + 16 + u16(offset + 24)
            if attr_size < 20 or first + attr_size * count > offset + size:
                raise ValueError("Invalid attributes")
            for index in range(count):
                at = first + index * attr_size
                name, raw, value_type, value = strings[u32(at + 4)], u32(at + 8), data[at + 15], u32(at + 16)
                attributes[name] = strings[raw] if raw != 0xffffffff else (strings[value] if value_type == 3 else value)
            if element == "manifest":
                root = attributes
            elif element == "uses-sdk":
                sdk = attributes
        offset += size
    if root.get("package") != PACKAGE or root.get("split"):
        raise ValueError("Wrong package or split APK")
    code, minimum = int(root["versionCode"]), int(sdk.get("minSdkVersion", 1))
    if not 0 < code < 2147483648 or root.get("versionCodeMajor", 0) or not 1 <= minimum <= 100:
        raise ValueError("Invalid version")
    return dict(version_code=code, version_name=str(root.get("versionName", code))[:100], min_sdk=minimum)


def inspect_apk(upload):
    if not upload.name.lower().endswith(".apk") or not 0 < upload.size <= MAX_APK_BYTES:
        raise ValidationError("ارفع ملف APK واحدًا لا يتجاوز 200 ميجابايت.")
    try:
        upload.seek(0)
        with zipfile.ZipFile(upload) as archive:
            info = archive.getinfo("AndroidManifest.xml")
            if info.file_size > 4 * 1024 * 1024 or "classes.dex" not in archive.namelist():
                raise ValueError("Invalid APK")
            metadata = manifest_metadata(archive.read(info))
        upload.seek(0)
        digest = hashlib.sha256()
        for chunk in upload.chunks():
            digest.update(chunk)
        metadata.update(sha256=digest.hexdigest(), size_bytes=upload.size)
        return metadata
    except (ValueError, KeyError, IndexError, struct.error, zipfile.BadZipFile, UnicodeError, RuntimeError) as exc:
        raise ValidationError("الملف ليس نسخة APK كاملة وصحيحة من التطبيق الشامل.") from exc
    finally:
        upload.seek(0)
