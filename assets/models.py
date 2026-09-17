from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

class Asset(models.Model):
    class Type(models.TextChoices):
        REGULAR_MACHINE = "REGULAR_MACHINE", "ماكينة عادية"
        PRESS = "PRESS", "مكبس"
        SPRING_MACHINE = "SPRING_MACHINE", "ماكينة سوستة"
    factory = models.ForeignKey("factories.Factory", on_delete=models.PROTECT, related_name="assets")
    asset_type = models.CharField("النوع", max_length=30, choices=Type.choices, db_index=True); asset_code = models.CharField("كود الماكينة", max_length=100)
    sequence_order = models.PositiveIntegerField("الترتيب", null=True, blank=True, db_index=True); is_active = models.BooleanField(default=True, db_index=True); is_archived = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True); updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["factory_id", "asset_type", "sequence_order", "id"]
        constraints = [models.UniqueConstraint(fields=["factory", "asset_code"], condition=Q(is_archived=False), name="uniq_live_asset_code_factory")]
        indexes = [models.Index(fields=["factory", "asset_type", "sequence_order"])]
    def clean(self):
        allowed = {"F1": {self.Type.REGULAR_MACHINE, self.Type.PRESS}, "F2": {self.Type.REGULAR_MACHINE, self.Type.SPRING_MACHINE}, "F3": {self.Type.REGULAR_MACHINE, self.Type.PRESS}}
        if self.factory_id and self.asset_type not in allowed.get(self.factory.code, set()): raise ValidationError({"asset_type": "نوع الماكينة غير مسموح في هذا المصنع."})
    def save(self, *args, **kwargs):
        self.full_clean()
        if self.sequence_order is None:
            last = Asset.objects.filter(factory=self.factory, asset_type=self.asset_type, is_archived=False).exclude(pk=self.pk).aggregate(models.Max("sequence_order"))["sequence_order__max"] or 0
            self.sequence_order = last + 1
        super().save(*args, **kwargs)
    def __str__(self): return self.asset_code
