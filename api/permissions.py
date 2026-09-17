from rest_framework.permissions import BasePermission
from accounts.models import User

class IsMaintenanceSupervisor(BasePermission):
    message = "هذه الخدمة متاحة لمشرفي الصيانة فقط."
    def has_permission(self, request, view): return bool(request.user.is_authenticated and request.user.is_active and request.user.role == User.Role.MAINTENANCE_SUPERVISOR and request.user.factory_id)

class IsAdminRole(BasePermission):
    def has_permission(self, request, view): return bool(request.user.is_authenticated and request.user.role == User.Role.ADMIN)
