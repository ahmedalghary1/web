from django.db import models

class Factory(models.Model):
    name = models.CharField("اسم المصنع", max_length=100, unique=True); code = models.CharField(max_length=20, unique=True); is_active = models.BooleanField(default=True)
    class Meta: verbose_name = "مصنع"; verbose_name_plural = "المصانع"
    def __str__(self): return self.name
