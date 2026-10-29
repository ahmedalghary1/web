from django.conf import settings
from rest_framework.permissions import BasePermission
from accounts.models import User
from accounts.shifts import get_user_effective_shift

class IsMaintenanceSupervisor(BasePermission):
    message = "هذه الخدمة متاحة لمشرفي الصيانة فقط."

    def has_permission(self, request, view):
        user = request.user
        if not (
            user.is_authenticated
            and user.is_active
            and user.factory_id
            and user.can_access_maintenance
        ):
            return False

        if getattr(user, "is_admin", user.is_superuser or user.role == User.Role.ADMIN):
            return True

        if getattr(settings, "ENFORCE_SHIFT_HOURS", True):
            shift = get_user_effective_shift(user)
            if shift != User.Shift.FIRST:
                self.message = "تقرير وخدمات الصيانة متاحة لمشرف الوردية الصباحية فقط."
                return False

        return True

class IsAdminRole(BasePermission):
    def has_permission(self, request, view): return bool(request.user.is_authenticated and request.user.role == User.Role.ADMIN)
