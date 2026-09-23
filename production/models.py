import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone

class Product(models.Model):
    factory = models.ForeignKey("factories.Factory", on_delete=models.CASCADE, related_name="products", verbose_name="المصنع")
    name = models.CharField("اسم المنتج", max_length=150)
    code = models.CharField("كود المنتج", max_length=50, blank=True, default="")
    weight_per_piece_grams = models.FloatField("وزن القطعة (جرام)", default=0.0, blank=True)
    is_active = models.BooleanField("نشط", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["factory", "name"]
        verbose_name = "منتج"
        verbose_name_plural = "المنتجات"

    def __str__(self):
        return f"{self.name} ({self.code})" if self.code else self.name


class MachineOperator(models.Model):
    factory = models.ForeignKey("factories.Factory", on_delete=models.CASCADE, related_name="operators", verbose_name="المصنع")
    name = models.CharField("اسم القائم على الماكينة", max_length=150)
    phone = models.CharField("رقم الهاتف", max_length=30, blank=True, default="")
    is_active = models.BooleanField("نشط", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["factory", "name"]
        verbose_name = "القائم على الماكينة"
        verbose_name_plural = "القائمون على الماكينات"

    def __str__(self):
        return self.name


class MachineProductionDefault(models.Model):
    asset = models.OneToOneField("assets.Asset", on_delete=models.CASCADE, related_name="production_default", verbose_name="الماكينة")
    default_product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL, related_name="default_machines", verbose_name="المنتج الافتراضي")
    default_operator = models.ForeignKey(MachineOperator, null=True, blank=True, on_delete=models.SET_NULL, related_name="default_machines", verbose_name="القائم على الماكينة الافتراضي")
    original_cavities = models.PositiveIntegerField("عدد اللقم الأصلي", default=1)
    cooling_time_seconds = models.FloatField("زمن التبريد (ثانية)", default=0.0)
    cycle_time_seconds = models.FloatField("زمن الدورة (ثانية)", default=0.0)
    target_cycle_production = models.FloatField("الإنتاج حسب زمن الدورة", default=0.0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "إعدادات إنتاج الماكينة"
        verbose_name_plural = "إعدادات إنتاج الماكينات"

    def __str__(self):
        return f"إعدادات إنتاج {self.asset.asset_code}"


class ProductionShiftReport(models.Model):
    class Shift(models.TextChoices):
        FIRST = "FIRST", "الوردية الأولى (صباحية)"
        SECOND = "SECOND", "الوردية الثانية (مسائية)"
        THIRD = "THIRD", "الوردية الثالثة (ليلية)"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "مسودة"
        PENDING_HANDOVER = "PENDING_HANDOVER", "بانتظار تأكيد استلام الوردية"
        CONFIRMED = "CONFIRMED", "تم الاستلام والاعتماد"

    client_report_id = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    factory = models.ForeignKey("factories.Factory", on_delete=models.PROTECT, related_name="production_reports", verbose_name="المصنع")
    supervisor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="submitted_production_reports", verbose_name="مشرف الوردية")
    shift = models.CharField("الوردية", max_length=20, choices=Shift.choices, default=Shift.FIRST)
    report_date = models.DateField("تاريخ الوردية", db_index=True)
    started_at_device = models.DateTimeField("بداية الوردية", null=True, blank=True)
    completed_at_device = models.DateTimeField("نهاية الوردية", null=True, blank=True)
    status = models.CharField("الحالة", max_length=30, choices=Status.choices, default=Status.PENDING_HANDOVER, db_index=True)
    
    # Handover fields
    handover_to_supervisor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="received_production_reports", verbose_name="المشرف المستلم")
    handover_confirmed_at = models.DateTimeField("تاريخ وتوقيت الاستلام", null=True, blank=True)
    handover_notes = models.TextField("ملاحظات الاستلام", blank=True, default="")
    general_notes = models.TextField("ملاحظات عامة عن الوردية", blank=True, default="")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-report_date", "-created_at"]
        verbose_name = "تقرير وردية الإنتاج"
        verbose_name_plural = "تقارير ورديات الإنتاج"
        constraints = [
            models.UniqueConstraint(fields=["factory", "report_date", "shift"], name="uniq_factory_date_shift")
        ]

    def __str__(self):
        return f"تقرير إنتاج {self.factory.name} - {self.get_shift_display()} ({self.report_date})"

    @property
    def total_production_weight_kg(self):
        return sum(entry.final_production_weight_kg for entry in self.machine_entries.all())

    @property
    def changed_products_count(self):
        return self.machine_entries.filter(product_changed=True).count()

    @property
    def changed_operators_count(self):
        return self.machine_entries.filter(operator_changed=True).count()


class MachineProductionEntry(models.Model):
    class OperationMode(models.TextChoices):
        AUTO = "AUTO", "أوتو"
        MANUAL = "MANUAL", "يدوي"

    report = models.ForeignKey(ProductionShiftReport, on_delete=models.CASCADE, related_name="machine_entries")
    asset = models.ForeignKey("assets.Asset", on_delete=models.PROTECT, related_name="production_entries", verbose_name="الماكينة")
    
    # Operator & Tracking of changes
    operator = models.ForeignKey(MachineOperator, null=True, blank=True, on_delete=models.SET_NULL, related_name="production_entries", verbose_name="القائم على الماكينة")
    operator_name = models.CharField("اسم القائم على الماكينة", max_length=150, blank=True, default="")
    original_operator = models.ForeignKey(MachineOperator, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="القائم على الماكينة الأصلي قبل التغيير")
    original_operator_name = models.CharField("القائم على الماكينة قبل التغيير", max_length=150, blank=True, default="")
    operator_changed = models.BooleanField("تم تغيير القائم على الماكينة", default=False)
    
    # Product & Tracking of changes
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL, related_name="active_entries", verbose_name="المنتج الحالي")
    product_name = models.CharField("اسم المنتج", max_length=150, blank=True, default="")
    original_product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="المنتج الأصلي قبل التغيير")
    original_product_name = models.CharField("المنتج قبل التغيير", max_length=150, blank=True, default="")
    product_changed = models.BooleanField("تم تغيير المنتج", default=False)
    
    # Cavities
    original_cavities = models.PositiveIntegerField("عدد اللقم الأصلي", default=1)
    current_cavities = models.PositiveIntegerField("عدد اللقم الحالية", default=1)
    
    # Operation Mode
    operation_mode = models.CharField("حالة التشغيل", max_length=10, choices=OperationMode.choices, default=OperationMode.AUTO)
    
    # Times (Dashboard only)
    cooling_time_seconds = models.FloatField("التبريد (ثانية)", default=0.0)
    cycle_time_seconds = models.FloatField("الدورة (ثانية)", default=0.0)
    
    # Materials & Output
    raw_material = models.CharField("الخامة المستخدمة", max_length=150, blank=True, default="")
    final_production_weight_kg = models.FloatField("وزن الإنتاج النهائي بالكيلو", default=0.0)
    target_cycle_production = models.FloatField("الإنتاج حسب زمن الدورة", default=0.0)
    packaging_type = models.CharField("العبوة", max_length=100, blank=True, default="")
    notes = models.TextField("ملاحظات الماكينة", blank=True, default="")

    class Meta:
        ordering = ["asset__sequence_order", "id"]
        verbose_name = "سجل إنتاج ماكينة"
        verbose_name_plural = "سجلات إنتاج الماكينات"

    def __str__(self):
        return f"{self.asset.asset_code} - {self.product_name or 'بدون منتج'}"

    @property
    def display_operator(self):
        if self.operator_name:
            return self.operator_name
        if self.operator_id and self.operator:
            return self.operator.name
        return "-"

    @property
    def display_product(self):
        if self.product_name:
            return self.product_name
        if self.product_id and self.product:
            return self.product.name
        return "-"


class ProductionStoppage(models.Model):
    class StoppageType(models.TextChoices):
        MACHINE_BREAKDOWN = "MACHINE_BREAKDOWN", "عطل ماكينة"
        MOLD_CHANGE = "MOLD_CHANGE", "تغيير اسطمبة / منتج"
        FRIDAY_PRAYER = "FRIDAY_PRAYER", "إيقاف صلاة الجمعة لجميع الماكينات"
        POWER_OUTAGE = "POWER_OUTAGE", "انقطاع كهرباء عام"
        RAW_MATERIAL_SHORTAGE = "RAW_MATERIAL_SHORTAGE", "نقص خامات أو مياه تبريد"
        OTHER = "OTHER", "توقف آخر"

    report = models.ForeignKey(ProductionShiftReport, on_delete=models.CASCADE, related_name="stoppages")
    asset = models.ForeignKey("assets.Asset", null=True, blank=True, on_delete=models.SET_NULL, related_name="stoppages", verbose_name="الماكينة (فارغ إذا كان للمصنع كاملاً)")
    stoppage_type = models.CharField("نوع التوقف / العطل", max_length=30, choices=StoppageType.choices, default=StoppageType.MACHINE_BREAKDOWN)
    description = models.TextField("وصف العطل أو سبب التوقف")
    duration_minutes = models.PositiveIntegerField("مدة التوقف (بالدقائق)", default=0)
    action_taken = models.TextField("الإجراء المتخذ / الحل", blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "عطل أو توقف"
        verbose_name_plural = "الأعطال والتوقفات"

    def __str__(self):
        machine_info = self.asset.asset_code if self.asset else "المصنع كاملاً"
        return f"{self.get_stoppage_type_display()} - {machine_info}"
