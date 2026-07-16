import os
from flask import Flask, redirect, url_for
from flask_login import LoginManager
from .models import db
from .database import init_app

login_manager = LoginManager()
login_manager.login_view = 'auth.login'  # will be created in auth blueprint


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    db_url = os.environ.get('DATABASE_URL')
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url or 'sqlite:///caroai.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    init_app(app)
    login_manager.init_app(app)

    # User loader callback
    from .models import Usuario  # Import here to avoid circular import

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(Usuario, int(user_id))

    # Register blueprints
    from .routes.tables import tables_bp
    from .routes.sales import sales_bp
    from .routes.inventory import inventory_bp
    from .routes.reports import reports_bp
    from .routes.auth import auth_bp

    app.register_blueprint(tables_bp, url_prefix='/tables')
    app.register_blueprint(sales_bp, url_prefix='/sales')
    app.register_blueprint(inventory_bp, url_prefix='/inventory')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(auth_bp, url_prefix='/auth')

    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))
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