from django import forms
from .models import MachineProductionDefault, Product, MachineOperator, ProductionOption

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

