import logging
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required
from ..models import Usuario
from werkzeug.security import check_password_hash

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        logger.info("Login GET — ya autenticado, redirigiendo a POS")
        return redirect(url_for('pos.index'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        logger.info(f"POST login — email={email}")

        if not email or not password:
            flash('Por favor, ingrese correo electrónico y contraseña.', 'warning')
            return redirect(url_for('auth.login'))

        user = Usuario.query.filter_by(email=email).first()

        if user:
            logger.info(f"Usuario encontrado: id={user.id}, email={user.email}, activo={user.activo}")
            if user.check_password(password):
                logger.info(f"check_password OK — login_user con remember=True")
                login_user(user, remember=True)
                flash('Inicio de sesión exitoso.', 'success')
                next_page = request.args.get('next')
                return redirect(next_page or url_for('pos.index'))
            else:
                logger.warning(f"check_password FALLÓ para email={email}")
        else:
            logger.warning(f"Usuario NO encontrado: email={email}")

        flash('Correo electrónico o contraseña inválidos.', 'danger')

    return render_template('auth/login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Ha cerrado sesión exitosamente.', 'success')
    return redirect(url_for('auth.login'))