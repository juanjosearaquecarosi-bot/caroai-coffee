from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default='employee')  # admin / employee
    activo = db.Column(db.Boolean, nullable=False, default=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        return self.activo

# The rest of the models follow...

class Producto(db.Model):
    __tablename__ = 'productos'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    categoria = db.Column(db.String(20), nullable=False)  # bebida / comida
    precio_venta_cop = db.Column(db.Integer, nullable=False)  # precio final en COP (IVA incluido)
    # relationship to recetas
    recetas = db.relationship('Receta', back_populates='producto', cascade='all, delete-orphan')

class Insumo(db.Model):
    __tablename__ = 'insumos'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    unidad_medida = db.Column(db.String(20), nullable=False)  # kg, g, ml, l, unidad
    costo_unitario_cop = db.Column(db.Integer, nullable=False)  # costo por unidad en COP
    stock_actual = db.Column(db.Integer, nullable=False, default=0)
    stock_minimo = db.Column(db.Integer, nullable=False, default=0)
    # relationship to movimientos
    movimientos = db.relationship('MovimientoInventario', back_populates='insumo', cascade='all, delete-orphan')
    # relationship to recetas
    recetas = db.relationship('Receta', back_populates='insumo', cascade='all, delete-orphan')

class TasaCambio(db.Model):
    __tablename__ = 'tasas_cambio'
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False, unique=True)
    tasa_cop_usd = db.Column(db.Float, nullable=False)  # COP per 1 USD
    tasa_tienda_bs_usd = db.Column(db.Float, nullable=False)  # Bs per USD (real rate used)

class Mesa(db.Model):
    __tablename__ = 'mesas'
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(10), unique=True, nullable=False)
    estado = db.Column(db.String(20), nullable=False, default='libre')  # libre / ocupada / cerrada
    fecha_apertura = db.Column(db.DateTime, nullable=True)
    fecha_cierre = db.Column(db.DateTime, nullable=True)
    # relationship to pedidos
    pedidos = db.relationship('Pedido', back_populates='mesa', cascade='all, delete-orphan')

class Pedido(db.Model):
    __tablename__ = 'pedidos'
    id = db.Column(db.Integer, primary_key=True)
    mesa_id = db.Column(db.Integer, db.ForeignKey('mesas.id'), nullable=False)
    fecha_hora = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    estado = db.Column(db.String(20), nullable=False, default='abierto')  # abierto / cerrado
    moneda_recibida = db.Column(db.String(10), nullable=False)  # COP / Bs / USD / Binance / tarjeta
    monto_recibido = db.Column(db.Integer, nullable=False)  # monto en la moneda original recibida
    tasa_id = db.Column(db.Integer, db.ForeignKey('tasas_cambio.id'), nullable=False)
    # relationship
    mesa = db.relationship('Mesa', back_populates='pedidos')
    tasa = db.relationship('TasaCambio')
    items = db.relationship('PedidoItem', back_populates='pedido', cascade='all, delete-orphan')

class PedidoItem(db.Model):
    __tablename__ = 'pedido_items'
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedidos.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    precio_unitario_cop = db.Column(db.Integer, nullable=False)  # precio del producto en COP al momento de la venta
    subtotal_cop = db.Column(db.Integer, nullable=False)  # cantidad * precio_unitario_cop
    # relationships
    pedido = db.relationship('Pedido', back_populates='items')
    producto = db.relationship('Producto')

class Receta(db.Model):
    __tablename__ = 'recetas'
    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=False)
    insumo_id = db.Column(db.Integer, db.ForeignKey('insumos.id'), nullable=False)
    cantidad_usada_por_unidad = db.Column(db.Float, nullable=False)  # cuánto insumo consume 1 unidad del producto
    # relationships
    producto = db.relationship('Producto', back_populates='recetas')
    insumo = db.relationship('Insumo', back_populates='recetas')

class MovimientoInventario(db.Model):
    __tablename__ = 'movimientos_inventario'
    id = db.Column(db.Integer, primary_key=True)
    insumo_id = db.Column(db.Integer, db.ForeignKey('insumos.id'), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # entrada / salida / merma / ajuste
    cantidad = db.Column(db.Integer, nullable=False)
    costo_total = db.Column(db.Integer, nullable=False)  # relevante sobre todo en “entrada”
    fecha = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    motivo = db.Column(db.String(200), nullable=True)
    # relationship
    insumo = db.relationship('Insumo', back_populates='movimientos')