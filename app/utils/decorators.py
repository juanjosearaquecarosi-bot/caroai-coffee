from functools import wraps
from flask import flash, redirect, url_for, abort
from flask_login import current_user


def role_required(*roles):
    """
    Decorator that restricts access to views based on user roles.
    Usage: @role_required('admin') or @role_required('admin', 'employee')
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Por favor, inicie sesión para acceder.', 'warning')
                return redirect(url_for('auth.login'))
            if current_user.rol not in roles:
                flash('No tiene permisos para acceder a esta sección.', 'error')
                return redirect(url_for('pos.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator
