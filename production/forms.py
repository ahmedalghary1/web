from django import forms
from .models import MachineProductionDefault, Product, MachineOperator

class MachineProductionDefaultForm(forms.ModelForm):
    class Meta:
        model = MachineProductionDefault
        fields = [
            "default_product",
            "default_operator",
            "original_cavities",
            "cooling_time_seconds",
            "cycle_time_seconds",
            "target_cycle_production",
        ]
        widgets = {
            "default_product": forms.Select(attrs={"class": "form-control"}),
            "default_operator": forms.Select(attrs={"class": "form-control"}),
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

