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
    password = forms.CharField(label="كلمة المرور", required=False, widget=forms.PasswordInput)
    class Meta: model = User; fields = ["phone", "factory", "is_active"]
    def clean_password(self):
        value = self.cleaned_data.get("password")
        if not self.instance.pk and not value: raise forms.ValidationError("كلمة المرور مطلوبة للمستخدم الجديد.")
        return value
    def save(self, commit=True):
        user = super().save(commit=False); user.role = User.Role.MAINTENANCE_SUPERVISOR
        if self.cleaned_data.get("password"): user.set_password(self.cleaned_data["password"])
        if commit: user.save()
        return user

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
