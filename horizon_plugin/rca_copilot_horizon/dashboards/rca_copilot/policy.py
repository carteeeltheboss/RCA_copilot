def is_admin(request):
    user = getattr(request, "user", None)
    if getattr(user, "is_superuser", False):
        return True
    roles = getattr(user, "roles", []) or []
    return any(getattr(role, "name", role) == "admin" for role in roles)
