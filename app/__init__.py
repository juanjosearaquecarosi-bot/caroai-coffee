import os
import logging
from flask import Flask, redirect, url_for, flash
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from .models import db
from .database import init_app

login_manager = LoginManager()
login_manager.login_view = 'auth.login'  # will be created in auth blueprint
csrf = CSRFProtect()


def create_app():
    app = Flask(__name__)

    # ── Logging en producción ──
    gunicorn_logger = logging.getLogger('gunicorn.error')
    if gunicorn_logger.handlers:
        app.logger.handlers = gunicorn_logger.handlers
        app.logger.setLevel(gunicorn_logger.level)
    else:
        app.logger.setLevel(logging.INFO)

    # ProxyFix para que Flask genere URLs HTTPS correctas
    # en entornos con proxy inverso (Render, Railway, etc.)
    # x_for=1 confía en el primer X-Forwarded-For
    # x_proto=1 confía en el primer X-Forwarded-Proto (http→https)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    db_url = os.environ.get('DATABASE_URL')
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url or 'sqlite:///caroai.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # 1 hora

    init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # ── CSRF error handler amigable ──
    from flask_wtf.csrf import CSRFError

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        app.logger.warning(f'CSRF error: {e}')
        flash('La sesión expiró o el token de seguridad no es válido. Por favor, intenta de nuevo.', 'warning')
        return redirect(url_for('pos.index'))

    # ── Error handler 500 con logging ──
    @app.errorhandler(500)
    def handle_500(error):
        app.logger.error(f'Error 500: {error}', exc_info=True)
        return '<h1>Error interno del servidor</h1><p>Revisa los logs de Render para más detalles.</p>', 500

    # User loader callback
    from .models import Usuario  # Import here to avoid circular import

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(Usuario, int(user_id))

    # Register blueprints
    from .routes.sales import sales_bp
    from .routes.pos import pos_bp
    from .routes.inventory import inventory_bp
    from .routes.reports import reports_bp
    from .routes.auth import auth_bp
    from .routes.gastos import gastos_bp
    from .routes.tasas import tasas_bp
    from .routes.facturas import facturas_bp

    app.register_blueprint(sales_bp, url_prefix='/sales')
    app.register_blueprint(pos_bp)
    app.register_blueprint(inventory_bp, url_prefix='/inventory')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(gastos_bp, url_prefix='/gastos')
    app.register_blueprint(tasas_bp, url_prefix='/tasas')
    app.register_blueprint(facturas_bp, url_prefix='/facturas')

    @app.route('/')
    def index():
        return redirect(url_for('pos.index'))

    # CLI command to seed the database
    @app.cli.command("seed-db")
    def seed_db():
        """Seed the database with initial data (mesas, usuarios, insumos, productos, tasas, gastos)."""
        from .seed_data import seed
        from flask import current_app
        seed(app=current_app._get_current_object())
        print("Base de datos inicializada con datos de prueba.")

    # CLI command to create admin user
    @app.cli.command("create-admin")
    def create_admin():
        """Create an admin user."""
        from .models import Usuario, db
        email = input("Email del admin: ")
        password = input("Contraseña: ")
        name = input("Nombre: ")
        if Usuario.query.filter_by(email=email).first():
            print("Ya existe un usuario con ese email.")
            return
        user = Usuario(nombre=name, email=email, rol='admin')
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print("Usuario admin creado.")

    return app