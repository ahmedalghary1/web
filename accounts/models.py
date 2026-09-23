from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models

class UserManager(BaseUserManager):
    def create_user(self, phone, password=None, **extra):
        if not phone: raise ValueError("رقم الهاتف مطلوب")
        user = self.model(phone=phone.strip(), **extra); user.set_password(password); user.save(using=self._db); return user
    def create_superuser(self, phone, password=None, **extra):
        extra.update(role=User.Role.ADMIN, is_staff=True, is_superuser=True, is_active=True)
        return self.create_user(phone, password, **extra)

class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "👑 مسؤول عام (كافة الصلاحيات والمصانع)"
        MAINTENANCE_SUPERVISOR = "MAINTENANCE_SUPERVISOR", "🛠️ مشرف صيانة دورية (صلاحيات الصيانة لمصنعه فقط)"
        PRODUCTION_SUPERVISOR = "PRODUCTION_SUPERVISOR", "🏭 مشرف إنتاج وأعطال (صلاحيات الإنتاج والأعطال لمصنعه فقط)"
        GENERAL_SUPERVISOR = "GENERAL_SUPERVISOR", "⚡ مشرف عام للمصنع (صيانة وإنتاج لمصنعه فقط)"
    phone = models.CharField("رقم الهاتف", max_length=30, unique=True, db_index=True)
    name = models.CharField("اسم المستخدم", max_length=150, blank=True, default="")
    role = models.CharField("الدور والصلاحيات", max_length=32, choices=Role.choices, default=Role.MAINTENANCE_SUPERVISOR)
    factory = models.ForeignKey("factories.Factory", verbose_name="المصنع", null=True, blank=True, on_delete=models.PROTECT, related_name="users")
    is_active = models.BooleanField(default=True); is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True); updated_at = models.DateTimeField(auto_now=True)
    objects = UserManager(); USERNAME_FIELD = "phone"; REQUIRED_FIELDS = []

    @property
    def display_name(self):
        val = self.name.strip() if self.name else ""
        return val if val else self.phone

    @property
    def is_admin(self):
        return self.is_superuser or self.role == self.Role.ADMIN

    @property
    def can_access_maintenance(self):
        return self.is_superuser or self.role in {self.Role.ADMIN, self.Role.MAINTENANCE_SUPERVISOR, self.Role.GENERAL_SUPERVISOR}

    @property
    def can_access_production(self):
        return self.is_superuser or self.role in {self.Role.ADMIN, self.Role.PRODUCTION_SUPERVISOR, self.Role.GENERAL_SUPERVISOR}

    def __str__(self): return self.display_name
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.role in {self.Role.MAINTENANCE_SUPERVISOR, self.Role.PRODUCTION_SUPERVISOR, self.Role.GENERAL_SUPERVISOR} and not self.factory_id:
            raise ValidationError({"factory": "يجب ربط المشرف بمصنع ليتمكن من متابعة تقاريره."})

