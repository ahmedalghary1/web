from factories.models import Factory

def factories_context(request):
    """
    Context processor providing active factories and user role helpers to all templates.
    """
    if not hasattr(request, "user") or not request.user.is_authenticated:
        return {}

    user = request.user
    is_admin = getattr(user, "is_admin", user.is_superuser or getattr(user, "role", "") == "ADMIN")

    if is_admin:
        factories = list(Factory.objects.filter(is_active=True).order_by("id"))
        current_factory_id = str(request.session.get("production_factory_id", ""))
        return {
            "all_active_factories": factories,
            "current_factory_id": current_factory_id,
        }

    return {
        "all_active_factories": [user.factory] if getattr(user, "factory", None) else [],
        "current_factory_id": str(getattr(user, "factory_id", "") or ""),
    }
