from django import forms
from .apk import inspect_apk
from .models import AppRelease


class ReleaseForm(forms.Form):
    apk = forms.FileField(label="نسخة التطبيق (APK)", widget=forms.ClearableFileInput(attrs={"accept": ".apk"}))
    notes = forms.CharField(label="ما الجديد في النسخة؟", required=False, widget=forms.Textarea(attrs={"rows": 3}), max_length=10000)
    publish_now = forms.BooleanField(label="نشر النسخة للأجهزة بعد التحقق من الملف", required=False, initial=True)

    def clean_apk(self):
        upload = self.cleaned_data["apk"]
        self.metadata = inspect_apk(upload)
        if AppRelease.objects.filter(version_code__gte=self.metadata["version_code"]).exists():
            raise forms.ValidationError("يجب أن يكون رقم البناء داخل APK أعلى من جميع النسخ المرفوعة سابقًا.")
        return upload
