from django.conf import settings
from rest_framework.permissions import BasePermission
from accounts.models import User
from accounts.shifts import get_user_effective_shift

class IsMaintenanceSupervisor(BasePermission):
    message = "هذه الخدمة متاحة لمشرفي الصيانة فقط."

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            self.message = "سجّل الدخول بالحساب صاحب التقرير أولًا."
            return False
        if not user.is_active:
            self.message = "هذا الحساب موقوف. تواصل مع مسؤول النظام."
            return False
        if not user.factory_id:
            self.message = "الحساب غير مرتبط بمصنع. يجب تحديد المصنع من لوحة التحكم."
            return False
        if not user.can_access_maintenance:
            self.message = "الحساب لا يملك صلاحية الصيانة. يلزم دور مشرف صيانة أو مشرف عام للمصنع."
            return False

        if getattr(user, "is_admin", user.is_superuser or user.role == User.Role.ADMIN):
            return True

        # Reading a factory report does not require the current morning shift.
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return True

        if getattr(settings, "ENFORCE_SHIFT_HOURS", True):
            shift = get_user_effective_shift(user)
            if shift != User.Shift.FIRST:
                self.message = "تقرير وخدمات الصيانة متاحة لمشرف الوردية الصباحية فقط."
                return False

        return True

class IsAdminRole(BasePermission):
    def has_permission(self, request, view): return bool(request.user.is_authenticated and request.user.role == User.Role.ADMIN)
