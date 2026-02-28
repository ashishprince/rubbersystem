from functools import wraps
from django.http import HttpResponseForbidden
from django.shortcuts import render


def role_required(*group_names):
    """
    Decorator that restricts access to users belonging to specific groups.
    Superusers (Admin) bypass all checks.
    Usage: @role_required('Manager', 'Admin')
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                from django.conf import settings
                from django.shortcuts import redirect
                return redirect(settings.LOGIN_URL)
            # Superusers bypass all role checks
            if user.is_superuser:
                return view_func(request, *args, **kwargs)
            # Check if user belongs to any of the required groups
            if user.groups.filter(name__in=group_names).exists():
                return view_func(request, *args, **kwargs)
            return render(request, 'forbidden.html', status=403)
        return _wrapped_view
    return decorator


def get_user_role(user):
    """Return the role string for a user."""
    if user.is_superuser:
        return 'Admin'
    if user.groups.filter(name='Manager').exists():
        return 'Manager'
    if user.groups.filter(name='Tapper').exists():
        return 'Tapper'
    return 'Unknown'
