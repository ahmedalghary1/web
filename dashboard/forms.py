from django import forms
from django.contrib.auth.forms import AuthenticationForm
from accounts.models import User
from assets.models import Asset, AssetType

class PhoneAuthenticationForm(AuthenticationForm):
    username = forms.CharField(label="رقم الهاتف", widget=forms.TextInput(attrs={"placeholder": "رقم الهاتف", "autocomplete": "tel"}))
    password = forms.CharField(label="كلمة المرور", widget=forms.PasswordInput(attrs={"placeholder": "كلمة المرور"}))

class AssetTypeForm(forms.ModelForm):
    class Meta:
        model = AssetType
        fields = ["name", "code", "is_active"]
        labels = {
            "name": "اسم نوع الماكينة",
            "code": "الكود التعريفي (اختياري)",
            "is_active": "نشط",
        }
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "مثال: ماكينة حقن، ماكينة نفخ، مكبس، خط إنتاج..."}),
            "code": forms.TextInput(attrs={"placeholder": "اتركه فارغاً للتوليد التلقائي (مثال: INJECTION, BLOW...)"}),
        }
        help_texts = {
            "name": "الاسم الذي سيظهر لجميع الماكينات التابعة لهذا النوع في الموقع والتطبيق والتقارير.",
            "code": "كود فريد للنوع بالإنجليزية، يمكنك تركه فارغاً وسيتم توليده تلقائياً من الاسم.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["code"].required = False

class AssetForm(forms.ModelForm):
    class Meta:
        model = Asset
        fields = ["factory", "type_ref", "asset_code", "name", "sequence_order", "is_active"]
        labels = {
            "factory": "المصنع التابع له",
            "type_ref": "نوع الماكينة",
            "asset_code": "رقم أو كود الماكينة",
            "name": "اسم مخصص للماكينة (اختياري)",
            "sequence_order": "الترتيب في دورة الصيانة",
            "is_active": "الماكينة نشطة ومفعلة",
        }
        help_texts = {
            "type_ref": "اختر نوع الماكينة. يمكنك إضافة وتعديل أنواع الماكينات من صفحة أنواع الماكينات.",
            "asset_code": "رقم أو كود الماكينة داخل المصنع (مثال: 1، 2، M-01...).",
            "name": "اختياري: اتركه فارغاً ليتكون الاسم تلقائياً من (نوع الماكينة + الكود) مثل: ماكينة حقن 1، وسينعكس أي تعديل في النوع تلقائياً.",
        }
        widgets = {
            "asset_code": forms.TextInput(attrs={"placeholder": "مثال: 1 أو 2 أو M-01"}),
            "name": forms.TextInput(attrs={"placeholder": "اتركه فارغاً للاستخدام التلقائي لاسم النوع + الكود"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from assets.models import ensure_default_asset_types_if_empty
        try:
            ensure_default_asset_types_if_empty()
        except Exception:
            pass
        self.fields["type_ref"].queryset = AssetType.objects.filter(is_active=True)
        self.fields["type_ref"].empty_label = "--- اختر نوع الماكينة ---"
        self.fields["type_ref"].required = True
        self.fields["name"].required = False
        if self.instance and self.instance.pk:
            if not self.instance.type_ref and self.instance.asset_type:
                t = AssetType.objects.filter(code=self.instance.asset_type).first()
                if t:
                    self.initial["type_ref"] = t.pk

    def clean(self):
        cleaned_data = super().clean()
        type_ref = cleaned_data.get("type_ref")
        if type_ref:
            cleaned_data["asset_type"] = type_ref.code
            if self.instance:
                self.instance.asset_type = type_ref.code
        return cleaned_data
class SupervisorForm(forms.ModelForm):
    password = forms.CharField(
        label="كلمة المرور",
        required=False,
        widget=forms.PasswordInput(attrs={"placeholder": "اتركها فارغة إذا لم ترد التغيير", "autocomplete": "new-password"})
    )
    class Meta:
        model = User
        fields = ["name", "phone", "role", "factory", "shift", "is_active"]
        labels = {
            "name": "اسم المستخدم / المشرف",
            "phone": "رقم الهاتف (اسم الدخول)",
            "role": "الدور والصلاحيات الممنوحة",
            "factory": "المصنع المخصص له (لرؤية تقاريره فقط)",
            "shift": "الوردية المخصصة للمشرف",
            "is_active": "الحساب نشط ومفعل",
        }
        help_texts = {
            "factory": "اختر المصنع الذي يعمل به المشرف. لن يتمكن المشرف من استعراض أو إدخال أي تقارير إلا لهذا المصنع المخصص له فقط. (مسؤول النظام لا يحتاج لربطه بمصنع).",
            "role": "حدد ما إذا كان المشرف مسؤولاً عن الصيانة الدورية، أو الإنتاج والأعطال، أو الاثنين معاً.",
            "shift": "الوردية التي يعمل بها هذا المشرف (الوردية الأولى، الثانية، أو الثالثة). عند إنهاء المشرف لورديته، يظهر التقرير تلقائياً لمشرف الوردية التالية فوراً.",
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
