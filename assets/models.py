from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

class Asset(models.Model):
    class Type(models.TextChoices):
        REGULAR_MACHINE = "REGULAR_MACHINE", "ماكينة حقن"
        PRESS = "PRESS", "مكبس"
        SPRING_MACHINE = "SPRING_MACHINE", "ماكينة نفخ"
        OTHER = "OTHER", "نوع آخر / مخصص"

    factory = models.ForeignKey("factories.Factory", on_delete=models.PROTECT, related_name="assets")
    name = models.CharField("اسم الماكينة", max_length=150, blank=True, default="", db_index=True)
    asset_type = models.CharField("النوع", max_length=30, choices=Type.choices, default=Type.REGULAR_MACHINE, db_index=True)
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
        allowed = {
            "F1": {self.Type.REGULAR_MACHINE, self.Type.PRESS, self.Type.SPRING_MACHINE, self.Type.EXTRUDER, self.Type.PRINTING, self.Type.PACKAGING, self.Type.CRUSHER, self.Type.OTHER},
            "F2": {self.Type.REGULAR_MACHINE, self.Type.SPRING_MACHINE, self.Type.EXTRUDER, self.Type.PRINTING, self.Type.PACKAGING, self.Type.CRUSHER, self.Type.OTHER},
            "F3": {self.Type.REGULAR_MACHINE, self.Type.PRESS, self.Type.SPRING_MACHINE, self.Type.EXTRUDER, self.Type.PRINTING, self.Type.PACKAGING, self.Type.CRUSHER, self.Type.OTHER},
        }
        if self.factory_id and self.factory.code in allowed:
            if self.asset_type not in allowed[self.factory.code]:
                raise ValidationError({"asset_type": f"نوع الماكينة ({self.get_asset_type_display()}) غير مسموح في هذا المصنع."})

    def save(self, *args, **kwargs):
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
        if self.asset_type == self.Type.OTHER and self.custom_type_name.strip():
            return self.custom_type_name.strip()
        return self.get_asset_type_display()

    @property
    def display_name(self):
        if self.name and self.name.strip():
            return self.name.strip()
        code = self.asset_code.strip()
        if code.startswith("مكبس") or code.startswith("ماكينة") or code.startswith("خط"):
            return code
        if code.startswith("حقن") or code.startswith("نفخ"):
            return f"ماكينة {code}"
        if self.asset_type == self.Type.PRESS:
            return f"مكبس {code}"
        elif self.asset_type == self.Type.REGULAR_MACHINE:
            return f"ماكينة حقن {code}"
        elif self.asset_type == self.Type.SPRING_MACHINE:
            return f"ماكينة نفخ {code}"
        return f"{self.type_display} {code}"

    @property
    def maintenance_title(self):
        title_base = self.display_name
        if title_base.startswith("الصيانة الدورية"):
            return title_base
        if title_base.startswith("مكبس") or title_base.startswith("ماكينة") or title_base.startswith("خط"):
            return f"الصيانة الدورية ل{title_base}"
        if title_base.startswith("حقن") or title_base.startswith("نفخ"):
            return f"الصيانة الدورية لماكينة {title_base}"
        return f"الصيانة الدورية لـ {title_base}"

    @property
    def production_title(self):
        title_base = self.display_name
        if title_base.startswith("إنتاج"):
            return title_base
        if title_base.startswith("مكبس") or title_base.startswith("ماكينة") or title_base.startswith("خط"):
            return f"إنتاج {title_base}"
        if title_base.startswith("حقن") or title_base.startswith("نفخ"):
            return f"إنتاج ماكينة {title_base}"
        return f"إنتاج {title_base}"

