from django import forms
from django.contrib.auth.forms import AuthenticationForm
from accounts.models import User
from assets.models import Asset

class PhoneAuthenticationForm(AuthenticationForm):
    username = forms.CharField(label="رقم الهاتف", widget=forms.TextInput(attrs={"placeholder": "رقم الهاتف", "autocomplete": "tel"}))
    password = forms.CharField(label="كلمة المرور", widget=forms.PasswordInput(attrs={"placeholder": "كلمة المرور"}))
class AssetForm(forms.ModelForm):
    class Meta: model = Asset; fields = ["factory", "asset_type", "asset_code", "sequence_order", "is_active"]
class SupervisorForm(forms.ModelForm):
    password = forms.CharField(
        label="كلمة المرور",
        required=False,
        widget=forms.PasswordInput(attrs={"placeholder": "اتركها فارغة إذا لم ترد التغيير", "autocomplete": "new-password"})
    )
    class Meta:
        model = User
        fields = ["name", "phone", "role", "factory", "is_active"]
        labels = {
            "name": "اسم المستخدم / المشرف",
            "phone": "رقم الهاتف (اسم الدخول)",
            "role": "الدور والصلاحيات الممنوحة",
            "factory": "المصنع المخصص له (لرؤية تقاريره فقط)",
            "is_active": "الحساب نشط ومفعل",
        }
        help_texts = {
            "factory": "اختر المصنع الذي يعمل به المشرف. لن يتمكن المشرف من استعراض أو إدخال أي تقارير إلا لهذا المصنع المخصص له فقط. (مسؤول النظام لا يحتاج لربطه بمصنع).",
            "role": "حدد ما إذا كان المشرف مسؤولاً عن الصيانة الدورية، أو الإنتاج والأعطال، أو الاثنين معاً.",
        }
    def clean_password(self):
        value = self.cleaned_data.get("password")
        if not self.instance.pk and not value: raise forms.ValidationError("كلمة المرور مطلوبة للمستخدم الجديد.")
        return value
    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get("role")
        factory = cleaned_data.get("factory")
        if role != User.Role.ADMIN and not factory:
            self.add_error("factory", "يجب تحديد المصنع المخصص للمشرف ليقتصر على رؤية تقارير هذا المصنع فقط.")
        return cleaned_data
    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get("password"): user.set_password(self.cleaned_data["password"])
        if commit: user.save()
        return user


class AccountUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["name"]
        labels = {
            "name": "اسم المستخدم",
        }
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "أدخل اسم المستخدم الكامل", "required": "required", "class": "form-control"}),
        }

from maintenance.models import ChecklistTemplate

class ChecklistTemplateForm(forms.ModelForm):
    class Meta:
        model = ChecklistTemplate
        fields = ["code", "name", "is_active"]
        labels = {
            "code": "كود القائمة (إنجليزي)",
            "name": "اسم القائمة (عربي)",
            "is_active": "مفعل"
        }
