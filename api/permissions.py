from rest_framework.permissions import BasePermission
from accounts.models import User

class IsMaintenanceSupervisor(BasePermission):
    message = "هذه الخدمة متاحة لمشرفي الصيانة فقط."
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user.is_authenticated
            and user.is_active
            and user.factory_id
            and user.can_access_maintenance
        )

class IsAdminRole(BasePermission):
    def has_permission(self, request, view): return bool(request.user.is_authenticated and request.user.role == User.Role.ADMIN)
