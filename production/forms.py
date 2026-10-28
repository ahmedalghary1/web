import math

from django import forms
from .models import FactoryShiftRotation, MachineProductionDefault, Product, MachineOperator, ProductionOption


class FactoryShiftRotationForm(forms.ModelForm):
    class Meta:
        model = FactoryShiftRotation
        fields = ["first_shift", "second_shift", "third_shift", "week_starts_on", "effective_from"]
        labels = {
            "first_shift": "الوردية الأولى في التسلسل",
            "second_shift": "الوردية التالية",
            "third_shift": "الوردية الأخيرة",
            "week_starts_on": "بداية الأسبوع",
            "effective_from": "تاريخ أسبوع البداية",
        }
        widgets = {
            "first_shift": forms.Select(attrs={"class": "form-control"}),
            "second_shift": forms.Select(attrs={"class": "form-control"}),
            "third_shift": forms.Select(attrs={"class": "form-control"}),
            "week_starts_on": forms.Select(attrs={"class": "form-control"}),
            "effective_from": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
        }

    def clean(self):
        data = super().clean()
        shifts = [data.get("first_shift"), data.get("second_shift"), data.get("third_shift")]
        if all(shifts) and len(set(shifts)) != 3:
            raise forms.ValidationError("اختر كل وردية مرة واحدة في تسلسل التدوير.")
        start = data.get("effective_from")
        weekday = data.get("week_starts_on")
        if start and weekday is not None and start.weekday() != weekday:
            self.add_error("effective_from", "اختر تاريخًا يوافق يوم بداية الأسبوع المحدد.")
        return data


class SupervisorHandoverRouteForm(forms.ModelForm):
    class Meta:
        from .models import SupervisorHandoverRoute
        model = SupervisorHandoverRoute
        fields = ["supervisor", "receiver"]
        labels = {
            "supervisor": "المشرف المسلّم (الذي سينهي تقريره)",
            "receiver": "المشرف المستلم (الذي سيراجع ويعتمد التقرير)",
        }
        widgets = {
            "supervisor": forms.Select(attrs={"class": "form-control", "style": "width:100%; max-width:420px; padding:8px 12px; border-radius:6px; border:1px solid #ccc;"}),
            "receiver": forms.Select(attrs={"class": "form-control", "style": "width:100%; max-width:420px; padding:8px 12px; border-radius:6px; border:1px solid #ccc;"}),
        }

    def __init__(self, *args, factory=None, **kwargs):
        super().__init__(*args, **kwargs)
        from accounts.models import User
        supervisors = User.objects.filter(
            factory=factory, is_active=True, role__in=["PRODUCTION_SUPERVISOR", "GENERAL_SUPERVISOR"]
        ).order_by("name", "phone")
        for field in self.fields.values():
            field.queryset = supervisors
            field.label_from_instance = lambda u: f"{u.display_name} ({u.get_shift_display() if u.shift else 'بدون وردية'}) - {u.phone}"

class MachineProductionDefaultForm(forms.ModelForm):
    class Meta:
        model = MachineProductionDefault
        fields = [
            "default_product",
            "default_operator",
            "default_raw_material",
            "default_final_unit",
            "target_cycle_unit",
            "default_packaging",
            "original_cavities",
            "cooling_time_seconds",
            "cycle_time_seconds",
            "target_cycle_production",
        ]
        widgets = {
            "default_product": forms.Select(attrs={"class": "form-control"}),
            "default_operator": forms.Select(attrs={"class": "form-control"}),
            "default_raw_material": forms.Select(attrs={"class": "form-control"}),
            "default_final_unit": forms.Select(attrs={"class": "form-control"}),
            "target_cycle_unit": forms.Select(attrs={"class": "form-control"}),
            "default_packaging": forms.Select(attrs={"class": "form-control"}),
            "original_cavities": forms.NumberInput(attrs={"min": 1, "step": 1}),
            "cooling_time_seconds": forms.NumberInput(attrs={"min": 0, "step": 0.1}),
            "cycle_time_seconds": forms.NumberInput(attrs={"min": 0, "step": 0.1}),
            "target_cycle_production": forms.NumberInput(attrs={"min": 0, "step": 0.1}),
        }


    def __init__(self, *args, factory=None, **kwargs):
        super().__init__(*args, **kwargs)
        if factory:
            self.fields["default_product"].queryset = Product.objects.filter(factory=factory, is_active=True)
            self.fields["default_operator"].queryset = MachineOperator.objects.filter(factory=factory, is_active=True)
            self.fields["default_raw_material"].queryset = ProductionOption.objects.filter(factory=factory, category=ProductionOption.Category.RAW_MATERIAL, is_active=True)
            self.fields["default_final_unit"].queryset = ProductionOption.objects.filter(factory=factory, category=ProductionOption.Category.FINAL_UNIT, is_active=True)
            self.fields["target_cycle_unit"].queryset = ProductionOption.objects.filter(factory=factory, category=ProductionOption.Category.CYCLE_UNIT, is_active=True)
            self.fields["default_packaging"].queryset = ProductionOption.objects.filter(factory=factory, category=ProductionOption.Category.PACKAGING, is_active=True)

    def clean(self):
        cleaned = super().clean()
        cavities = cleaned.get("original_cavities")
        if cavities is not None and cavities < 1:
            self.add_error("original_cavities", "أدخل عدد لقم لا يقل عن 1.")
        for field in ("cooling_time_seconds", "cycle_time_seconds", "target_cycle_production"):
            value = cleaned.get(field)
            if value is not None and (not math.isfinite(value) or value < 0):
                self.add_error(field, "أدخل قيمة صحيحة لا تقل عن صفر.")
        return cleaned


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "code", "weight_per_piece_grams", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "اسم المنتج"}),
            "code": forms.TextInput(attrs={"placeholder": "كود المنتج (اختياري)"}),
            "weight_per_piece_grams": forms.NumberInput(attrs={"min": 0, "step": 0.01}),
            "is_active": forms.CheckboxInput(),
        }


class MachineOperatorForm(forms.ModelForm):
    class Meta:
        model = MachineOperator
        fields = ["name", "phone", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "اسم العامل / القائم على الماكينة"}),
            "phone": forms.TextInput(attrs={"placeholder": "رقم الهاتف (اختياري)"}),
            "is_active": forms.CheckboxInput(),
        }


class ProductionOptionForm(forms.ModelForm):
    class Meta:
        model = ProductionOption
        fields = ["name", "kg_per_unit", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "مثال: PP سابك 500P"}),
            "kg_per_unit": forms.NumberInput(attrs={"min": 0, "step": 0.001, "placeholder": "اتركه فارغاً إذا لم تُعرف معادلة التحويل"}),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, category=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.category = category
        if category != ProductionOption.Category.FINAL_UNIT:
            self.fields.pop("kg_per_unit")

    def clean_kg_per_unit(self):
        value = self.cleaned_data.get("kg_per_unit")
        if value is not None and value <= 0:
            raise forms.ValidationError("أدخل قيمة أكبر من صفر، أو اتركها فارغة إذا لم تعرف التحويل.")
        return value

