from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.text import slugify


class AssetType(models.Model):
    name = models.CharField("اسم نوع الماكينة", max_length=150, unique=True)
    code = models.CharField("كود النوع", max_length=50, unique=True, db_index=True)
    is_active = models.BooleanField("نشط", default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "نوع ماكينة"
        verbose_name_plural = "أنواع الماكينات"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.code:
            import uuid
            slug = slugify(self.name, allow_unicode=False)
            if not slug:
                slug = f"TYPE_{uuid.uuid4().hex[:6].upper()}"
            else:
                slug = slug.upper().replace("-", "_")
            base_slug = slug
            i = 1
            while AssetType.objects.filter(code=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}_{i}"
                i += 1
            self.code = slug

        old_name = None
        if self.pk:
            old_inst = AssetType.objects.filter(pk=self.pk).first()
            if old_inst and old_inst.name != self.name:
                old_name = old_inst.name

        super().save(*args, **kwargs)

        if old_name and old_name != self.name:
            # Sync name changes to assets whose name started with old_name
            assets_to_update = Asset.objects.filter(
                models.Q(type_ref=self) | models.Q(asset_type=self.code)
            )
            for a in assets_to_update:
                if a.name and a.name.startswith(old_name):
                    a.name = a.name.replace(old_name, self.name, 1)
                    a.save(update_fields=["name"])


def ensure_default_asset_types():
    defaults = [
        ("REGULAR_MACHINE", "ماكينة حقن"),
        ("PRESS", "مكبس"),
        ("SPRING_MACHINE", "ماكينة نفخ"),
        ("EXTRUDER", "ماكينة سحب / إكسترودر"),
        ("PRINTING", "ماكينة طباعة"),
        ("PACKAGING", "ماكينة تغليف / تعبئة"),
        ("CRUSHER", "كسارة / مطحنة"),
        ("OTHER", "نوع آخر / مخصص"),
    ]
    for code, name in defaults:
        AssetType.objects.get_or_create(code=code, defaults={"name": name})


def ensure_default_asset_types_if_empty():
    if not AssetType.objects.exists():
        ensure_default_asset_types()


class Asset(models.Model):
    class Type(models.TextChoices):
        REGULAR_MACHINE = "REGULAR_MACHINE", "ماكينة حقن"
        PRESS = "PRESS", "مكبس"
        SPRING_MACHINE = "SPRING_MACHINE", "ماكينة نفخ"
        EXTRUDER = "EXTRUDER", "ماكينة سحب / إكسترودر"
        PRINTING = "PRINTING", "ماكينة طباعة"
        PACKAGING = "PACKAGING", "ماكينة تغليف / تعبئة"
        CRUSHER = "CRUSHER", "كسارة / مطحنة"
        OTHER = "OTHER", "نوع آخر / مخصص"

    factory = models.ForeignKey("factories.Factory", on_delete=models.PROTECT, related_name="assets")
    name = models.CharField("اسم الماكينة", max_length=150, blank=True, default="", db_index=True)
    type_ref = models.ForeignKey(
        AssetType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assets",
        verbose_name="نوع الماكينة",
    )
    asset_type = models.CharField("النوع", max_length=50, choices=Type.choices, default=Type.REGULAR_MACHINE, db_index=True)
    custom_type_name = models.CharField("اسم النوع المخصص", max_length=100, blank=True, default="")
    asset_code = models.CharField("كود الماكينة", max_length=100)
    sequence_order = models.PositiveIntegerField("الترتيب", null=True, blank=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_archived = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["factory_id", "asset_type", "sequence_order", "id"]
        constraints = [models.UniqueConstraint(fields=["factory", "asset_code"], condition=Q(is_archived=False), name="uniq_live_asset_code_factory")]
        indexes = [models.Index(fields=["factory", "asset_type", "sequence_order"])]

    def clean(self):
        if self.factory_id and self.factory.code == "F2" and self.asset_type == self.Type.PRESS:
            raise ValidationError({"asset_type": f"نوع الماكينة ({self.get_asset_type_display()}) غير مسموح في هذا المصنع."})

    def save(self, *args, **kwargs):
        if self.type_ref and not self.asset_type:
            self.asset_type = self.type_ref.code
        elif self.type_ref and self.type_ref.code != self.asset_type:
            self.asset_type = self.type_ref.code
        elif self.asset_type and not self.type_ref:
            try:
                self.type_ref = AssetType.objects.filter(code=self.asset_type).first()
            except Exception:
                pass

        if not self.name and self.asset_code:
            self.name = self.asset_code.strip()
        elif not self.asset_code and self.name:
            self.asset_code = self.name.strip()
        self.full_clean()
        if self.sequence_order is None:
            last = Asset.objects.filter(factory=self.factory, asset_type=self.asset_type, is_archived=False).exclude(pk=self.pk).aggregate(models.Max("sequence_order"))["sequence_order__max"] or 0
            self.sequence_order = last + 1
        super().save(*args, **kwargs)

    def __str__(self):
        return self.display_name

    @property
    def type_display(self):
        if self.type_ref:
            return self.type_ref.name
        try:
            t = AssetType.objects.filter(code=self.asset_type).first()
            if t:
                return t.name
        except Exception:
            pass
        if self.asset_type == self.Type.OTHER and self.custom_type_name.strip():
            return self.custom_type_name.strip()
        for choice_val, choice_label in self.Type.choices:
            if choice_val == self.asset_type:
                return choice_label
        return self.asset_type

    def get_asset_type_display(self):
        return self.type_display

    @property
    def display_name(self):
        type_name = self.type_display
        code = (self.asset_code or "").strip()
        name = (self.name or "").strip()
        if name and name != code and name != f"{type_name} {code}":
            return name
        if not code:
            return type_name
        if code.startswith(type_name):
            return code
        return f"{type_name} {code}"

    @property
    def maintenance_title(self):
        title_base = self.display_name
        if title_base.startswith("الصيانة الدورية"):
            return title_base
        return f"الصيانة الدورية لـ {title_base}"

    @property
    def production_title(self):
        title_base = self.display_name
        if title_base.startswith("إنتاج"):
            return title_base
        return f"إنتاج {title_base}"
