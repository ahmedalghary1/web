from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from accounts.models import User
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    ordering = ["phone"]; list_display = ["name", "phone", "role", "factory", "is_active", "last_login"]; list_filter = ["role", "factory", "is_active"]; search_fields = ["name", "phone"]
    fieldsets = ((None, {"fields": ("phone", "name", "password")}), ("الصلاحيات", {"fields": ("role", "factory", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")}), ("التواريخ", {"fields": ("last_login", "created_at", "updated_at")}))
    readonly_fields = ["created_at", "updated_at", "last_login"]; add_fieldsets = ((None, {"classes": ("wide",), "fields": ("phone", "name", "password1", "password2", "role", "factory", "is_active", "is_staff")}),)
