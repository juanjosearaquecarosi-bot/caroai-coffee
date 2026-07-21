from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


# ──────────────────────────────────────────────
#  USUARIO (se mantiene igual)
# ──────────────────────────────────────────────
class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default='empleado')  # admin / empleado
    activo = db.Column(db.Boolean, nullable=False, default=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        return self.activo


# ──────────────────────────────────────────────
#  MESA — reemplaza a Ubicacion
#  Mesas, barra. Cada mesa tiene un pedido activo.
# ──────────────────────────────────────────────
class Mesa(db.Model):
    __tablename__ = 'mesas'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False)          # "Mesa 1", "Barra"
    estado = db.Column(db.String(20), nullable=False, default='libre')  # libre / ocupada
    fecha_apertura = db.Column(db.DateTime, nullable=True)

    pedidos = db.relationship('Pedido', back_populates='mesa', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Mesa {self.nombre} — {self.estado}>'


# ──────────────────────────────────────────────
#  PRODUCTO — catálogo del café
#  Almacena precios en COP, USD y Bs según el Excel.
# ──────────────────────────────────────────────
class Producto(db.Model):
    __tablename__ = 'productos'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.String(20), nullable=False, default='bebida')  # bebida / comida / grano / cerveza
    categoria = db.Column(db.String(20), nullable=False, default='bebida')  # same as tipo (legacy compat)
    precio_cop = db.Column(db.Integer, nullable=False, default=0)
    precio_usd = db.Column(db.Float, nullable=True)
    precio_bs = db.Column(db.Float, nullable=True)

    # Compatibilidad temporal con módulos legacy
    precio_venta_cop = db.Column(db.Integer, nullable=False, default=0)
    descuenta_inventario = db.Column(db.Boolean, nullable=False, default=False)
    insumo_id = db.Column(db.Integer, db.ForeignKey('insumos.id'), nullable=True)
    insumo = db.relationship('Insumo', foreign_keys=[insumo_id])

    items = db.relationship('PedidoItem', back_populates='producto')

    def __repr__(self):
        return f'<Producto {self.nombre} — ${self.precio_cop:,}>'


# ──────────────────────────────────────────────
#  PEDIDO (simplificado)
#  - Sin dependencia de tasa de cambio
#  - Estado: abierto / pagado / anulado
#  - moneda_pago: VES / COP / USD
#  - metodo_pago: efectivo / binance / bancolombia
#  - observaciones: para pagos digitales (Binance/Bancolombia)
#    se escribe aquí la plataforma y monto.
# ──────────────────────────────────────────────
class Pedido(db.Model):
    __tablename__ = 'pedidos'

    __table_args__ = (
        db.Index('ix_pedidos_fecha_estado', 'fecha_hora', 'estado'),
        db.Index('ix_pedidos_pagado_en', 'pagado_en'),
    )

    id = db.Column(db.Integer, primary_key=True)
    mesa_id = db.Column(db.Integer, db.ForeignKey('mesas.id'), nullable=False)
    fecha_hora = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    pagado_en = db.Column(db.DateTime, nullable=True)
    estado = db.Column(db.String(20), nullable=False, default='abierto')  # abierto / pagado / pendiente / anulado
    total = db.Column(db.Integer, nullable=False, default=0)

    # Información de pago
    moneda_pago = db.Column(db.String(10), nullable=True)     # VES / COP / USD
    metodo_pago = db.Column(db.String(20), nullable=True)     # efectivo / binance / pago_movil
    tasa_aplicada = db.Column(db.Float, nullable=True)        # tasa usada para convertir: 1 USD = X COP o 1 BS = X COP
    total_pagado_moneda = db.Column(db.Float, nullable=True)  # total pagado en la moneda seleccionada (USD, BS o COP)
    observaciones = db.Column(db.String(300), nullable=True)

    # Relaciones
    mesa = db.relationship('Mesa', back_populates='pedidos')
    items = db.relationship('PedidoItem', back_populates='pedido', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Pedido #{self.id} — {self.estado} — ${self.total:,}>'


# ──────────────────────────────────────────────
#  PEDIDO ITEM (detalle de productos vendidos)
#  Cada línea es un producto vendido en el pedido.
# ──────────────────────────────────────────────
class PedidoItem(db.Model):
    __tablename__ = 'pedido_items'

    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedidos.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False, default=1)
    precio_unitario_cop = db.Column(db.Integer, nullable=False)
    subtotal_cop = db.Column(db.Integer, nullable=False)

    # Anulación lógica (para pedidos ya pagados/cerrados)
    anulado_en = db.Column(db.DateTime, nullable=True)
    motivo_anulacion = db.Column(db.String(200), nullable=True)

    # Relaciones
    pedido = db.relationship('Pedido', back_populates='items')
    producto = db.relationship('Producto', back_populates='items')

    @property
    def anulado(self):
        return self.anulado_en is not None

    def __repr__(self):
        return f'<Item {self.producto.nombre if self.producto else "?"} x{self.cantidad}>'


# ──────────────────────────────────────────────
#  INSUMO (insumos para inventario)
# ──────────────────────────────────────────────
class Insumo(db.Model):
    __tablename__ = 'insumos'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    unidad_medida = db.Column(db.String(20), nullable=False)  # kg / g / ml / l / unidad
    costo_unitario_cop = db.Column(db.Integer, nullable=False)
    stock_actual = db.Column(db.Integer, nullable=False, default=0)
    stock_minimo = db.Column(db.Integer, nullable=False, default=0)

    movimientos = db.relationship('MovimientoInventario', back_populates='insumo',
                                  cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Insumo {self.nombre} — stock: {self.stock_actual} {self.unidad_medida}>'


# ──────────────────────────────────────────────
#  MOVIMIENTO DE INVENTARIO
#  entrada / salida / merma / ajuste
# ──────────────────────────────────────────────
class MovimientoInventario(db.Model):
    __tablename__ = 'movimientos_inventario'

    id = db.Column(db.Integer, primary_key=True)
    insumo_id = db.Column(db.Integer, db.ForeignKey('insumos.id'), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)        # entrada / salida / merma / ajuste
    cantidad = db.Column(db.Integer, nullable=False)
    costo_total = db.Column(db.Integer, nullable=False)    # relevante en "entrada"
    fecha = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    motivo = db.Column(db.String(200), nullable=True)

    insumo = db.relationship('Insumo', back_populates='movimientos')

    def __repr__(self):
        return f'<Mov {self.tipo} — {self.cantidad} {self.insumo.unidad_medida if self.insumo else ""}>'


# ──────────────────────────────────────────────
#  GASTO (NUEVO)
#  Registro de gastos operativos del negocio:
#  Nómina, Insumos (leche, pastelería), Mantenimiento.
# ──────────────────────────────────────────────
class Gasto(db.Model):
    __tablename__ = 'gastos'

    id = db.Column(db.Integer, primary_key=True)
    concepto = db.Column(db.String(200), nullable=False)                     # descripción del gasto
    categoria = db.Column(db.String(20), nullable=False)                     # nomina / insumos / mantenimiento
    monto = db.Column(db.Integer, nullable=False)                            # monto numérico
    moneda = db.Column(db.String(10), nullable=False, default='COP')         # VES / COP / USD
    observaciones = db.Column(db.String(300), nullable=True)               # nota opcional
    fecha = db.Column(db.Date, nullable=False, default=date.today)           # fecha del gasto
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f'<Gasto {self.concepto[:40]} — ${self.monto:,} {self.moneda}>'


# ──────────────────────────────────────────────
#  FACTURA (control de cuentas por pagar)
#  Registro de facturas de proveedores con
#  control de fechas de vencimiento.
# ──────────────────────────────────────────────
class Factura(db.Model):
    __tablename__ = 'facturas'

    id = db.Column(db.Integer, primary_key=True)
    referencia = db.Column(db.String(50), unique=True, nullable=False)
    empresa = db.Column(db.String(100), nullable=False)
    fecha_recibida = db.Column(db.Date, nullable=False)
    dias_credito = db.Column(db.Integer, nullable=False, default=0)
    fecha_vencimiento = db.Column(db.Date, nullable=False)  # fecha_recibida + dias_credito
    estado = db.Column(db.String(20), nullable=False, default='pendiente')  # pendiente / pagada
    fecha_pago = db.Column(db.Date, nullable=True)
    monto = db.Column(db.Integer, nullable=True)  # en COP
    notas = db.Column(db.String(300), nullable=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f'<Factura {self.referencia} — {self.empresa} — {self.estado}>'


# ──────────────────────────────────────────────
#  TASA DE CAMBIO (Fase 4)
#  Registro de tasas de referencia para conversión
#  entre monedas. NO se usa automáticamente en
#  reportes; se muestra de forma informativa.
# ──────────────────────────────────────────────
class TasaCambio(db.Model):
    __tablename__ = 'tasas_cambio'

    id = db.Column(db.Integer, primary_key=True)
    moneda_origen = db.Column(db.String(10), nullable=False)   # VES / COP / USD
    moneda_destino = db.Column(db.String(10), nullable=False)  # VES / COP / USD
    tasa = db.Column(db.Float, nullable=False)                  # 1 moneda_origen = tasa moneda_destino
    vigente_desde = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f'<Tasa 1 {self.moneda_origen} = {self.tasa} {self.moneda_destino} (desde {self.vigente_desde.strftime("%d/%m/%Y")})>'
