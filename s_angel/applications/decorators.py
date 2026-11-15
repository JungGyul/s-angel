"""Access policy for the site's staff pages."""
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.shortcuts import render
from django.urls import reverse


def custom_staff_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), reverse('users:main'))
        if not (request.user.is_active and request.user.is_staff):
            return render(request, 'access_denied.html', status=403)
        return view(request, *args, **kwargs)
    return wrapped
