from django.conf import settings


def allauth_settings(request):
    """Expose some settings from django-allauth in templates."""
    return {
        "ACCOUNT_ALLOW_REGISTRATION": settings.ACCOUNT_ALLOW_REGISTRATION,
    }


def nav_section(request):
    """Which primary navigation tab is active for the current URL (used by layouts/app.html)."""
    path = request.path or ""
    if "/calendar" in path:
        section = "calendar"
    elif "/accounting" in path or "/admin/budget-year" in path or "/admin/accounting" in path:
        section = "accounting"
    elif "/profile" in path:
        section = "profile"
    elif "/special-lotteries" in path:
        section = "lottery"
    elif "/admin-page" in path or "/user/" in path:
        section = "admin"
    else:
        section = "home"
    return {"nav_section": section}
