"""
seed_data.py  —  Inicializa la base de datos con datos de prueba.

Uso:  python seed_data.py
"""

import os
from flask import Flask
from app.models import (
    db, Usuario, Mesa, Producto, Insumo,
    TasaCambio, Gasto,
)
from datetime import datetime, date



def _minimal_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'seed-only'
    db_url = os.environ.get('DATABASE_URL')
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url or 'sqlite:///caroai.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app


def seed(app=None):
    if app is None:
        app = _minimal_app()

    with app.app_context():
        # Crear tablas si no existen (nunca dropear)
        db.create_all()
        print("✔  Tablas aseguradas (create_all).")
        print()

        # 1. USUARIOS (solo si no existen)
        if Usuario.query.count() == 0:
            admin = Usuario(nombre='Admin Caroai', email='admin@caroai.com', rol='admin')
            admin.set_password('admin123')
            empleado = Usuario(nombre='Empleado Caroai', email='empleado@caroai.com', rol='empleado')
            empleado.set_password('empleado123')
            db.session.add_all([admin, empleado])
            db.session.commit()
            print("✔  Usuarios creados: admin@caroai.com / empleado@caroai.com")
        else:
            print("ℹ️  Usuarios ya existen — omitido.")

        # 2. MESAS (solo si no existen)
        if Mesa.query.count() == 0:
            mesas = [
                Mesa(nombre='Mesa 1'),
                Mesa(nombre='Mesa 2'),
                Mesa(nombre='Mesa 3'),
                Mesa(nombre='Mesa 4'),
                Mesa(nombre='Mesa 5'),
                Mesa(nombre='Mesa 6'),
                Mesa(nombre='Barra'),
            ]
            db.session.add_all(mesas)
            db.session.commit()
            print("✔  Mesas creadas: 6 mesas + 1 barra")
        else:
            print(f"ℹ️  Mesas ya existen ({Mesa.query.count()}) — omitido.")

        # 3. INSUMOS (solo si no existen)
        if Insumo.query.count() == 0:
            insumos = [
                Insumo(nombre='Café en grano x kg',   unidad_medida='kg',    costo_unitario_cop=72000, stock_actual=10, stock_minimo=2),
                Insumo(nombre='Leche entera x 900ml', unidad_medida='l',     costo_unitario_cop=3000,  stock_actual=15, stock_minimo=5),
                Insumo(nombre='Refresco lata x 355ml',unidad_medida='unidad',costo_unitario_cop=1800,  stock_actual=48, stock_minimo=12),
                Insumo(nombre='Pastel entero x 10porc',unidad_medida='unidad',costo_unitario_cop=25000, stock_actual=4,  stock_minimo=1),
            ]
            db.session.add_all(insumos)
            db.session.commit()
            print("✔  4 insumos base con stock inicial")
        else:
            print(f"ℹ️  Insumos ya existen ({Insumo.query.count()}) — omitido.")

        # 4. TASAS DE CAMBIO (solo si no existen)
        if TasaCambio.query.count() == 0:
            tasas = [
                TasaCambio(moneda_origen='USD', moneda_destino='COP', tasa=4200.0, vigente_desde=datetime(2026, 7, 1, 0, 0, 0)),
                TasaCambio(moneda_origen='VES', moneda_destino='COP', tasa=6.0, vigente_desde=datetime(2026, 7, 1, 0, 0, 0)),
            ]
            db.session.add_all(tasas)
            db.session.commit()
            print("✔  2 tasas de cambio: 1 COP = 0.000238 USD, 1 COP = 0.18 VES")
        else:
            print(f"ℹ️  Tasas de cambio ya existen ({TasaCambio.query.count()}) — omitido.")

        # 5. GASTOS DE EJEMPLO (solo si no existen)
        if Gasto.query.count() == 0:
            gastos = [
                Gasto(concepto='Pago nómina mes julio', categoria='nomina', monto=2400000, moneda='COP', fecha=date(2026, 7, 15)),
                Gasto(concepto='Compra leche fresca Alpina', categoria='insumos', monto=45000, moneda='COP', fecha=date(2026, 7, 10), observaciones='15 unidades x 900ml'),
                Gasto(concepto='Reparación máquina espresso', categoria='mantenimiento', monto=180000, moneda='COP', fecha=date(2026, 7, 8)),
                Gasto(concepto='Pago factura internet', categoria='mantenimiento', monto=35, moneda='USD', fecha=date(2026, 7, 5), observaciones='Pago mensual proveedor'),
            ]
            db.session.add_all(gastos)
            db.session.commit()
            print("✔  4 gastos de ejemplo (nómina, insumos, mantenimiento COP y USD)")
        else:
            print(f"ℹ️  Gastos ya existen ({Gasto.query.count()}) — omitido.")

        # 6. PRODUCTOS (solo si no existen)
        if Producto.query.count() == 0:
            try:
                from app.utils.excel_import import import_productos
                ins, act = import_productos()
                if ins == 0 and act == 0:
                    raise ImportError('No Excel found')
                print(f"✔  {ins} productos insertados desde Excel, {act} actualizados.")
            except Exception as e:
                print(f"   ℹ️  Importación desde Excel: {e}")
                db.session.rollback()
                print("   → Usando productos de ejemplo como fallback.")
                # Si no hay Excel, crear productos del Excel como fallback
                productos = [
                    # BEBIDAS (24)
                    Producto(nombre='Agua mineral 620 ml', tipo='bebida', categoria='bebida', precio_cop=3000, precio_venta_cop=3000, precio_usd=0.83, precio_bs=666.67),
                    Producto(nombre='Batidos (Fresa/Mora)', tipo='bebida', categoria='bebida', precio_cop=5000, precio_venta_cop=5000, precio_usd=1.39, precio_bs=1111.11),
                    Producto(nombre='Café Americano', tipo='bebida', categoria='bebida', precio_cop=4500, precio_venta_cop=4500, precio_usd=1.25, precio_bs=1000.0),
                    Producto(nombre='Cappuccino / Latte', tipo='bebida', categoria='bebida', precio_cop=6500, precio_venta_cop=6500, precio_usd=1.81, precio_bs=1444.44),
                    Producto(nombre='Cappuccino Peq', tipo='bebida', categoria='bebida', precio_cop=5000, precio_venta_cop=5000, precio_usd=1.39, precio_bs=1111.11),
                    Producto(nombre='Cappuccino doble', tipo='bebida', categoria='bebida', precio_cop=8000, precio_venta_cop=8000, precio_usd=2.22, precio_bs=1777.78),
                    Producto(nombre='Caroai Bombon', tipo='bebida', categoria='bebida', precio_cop=5500, precio_venta_cop=5500, precio_usd=1.53, precio_bs=1222.22),
                    Producto(nombre='Caroai frappe', tipo='bebida', categoria='bebida', precio_cop=12000, precio_venta_cop=12000, precio_usd=3.33, precio_bs=2666.67),
                    Producto(nombre='Chocolate caliente', tipo='bebida', categoria='bebida', precio_cop=6500, precio_venta_cop=6500, precio_usd=1.81, precio_bs=1444.44),
                    Producto(nombre='Doppio', tipo='bebida', categoria='bebida', precio_cop=5000, precio_venta_cop=5000, precio_usd=1.39, precio_bs=1111.11),
                    Producto(nombre='Espresso', tipo='bebida', categoria='bebida', precio_cop=4000, precio_venta_cop=4000, precio_usd=1.11, precio_bs=888.89),
                    Producto(nombre='Espresso americano', tipo='bebida', categoria='bebida', precio_cop=4500, precio_venta_cop=4500, precio_usd=1.25, precio_bs=1000.0),
                    Producto(nombre='Frappe de café y limón', tipo='bebida', categoria='bebida', precio_cop=6500, precio_venta_cop=6500, precio_usd=1.81, precio_bs=1444.44),
                    Producto(nombre='Frappe de limón/Masato', tipo='bebida', categoria='bebida', precio_cop=3000, precio_venta_cop=3000, precio_usd=0.83, precio_bs=666.67),
                    Producto(nombre='Infusiones', tipo='bebida', categoria='bebida', precio_cop=3600, precio_venta_cop=3600, precio_usd=1.0, precio_bs=800.0),
                    Producto(nombre='Latte canela', tipo='bebida', categoria='bebida', precio_cop=7500, precio_venta_cop=7500, precio_usd=2.08, precio_bs=1666.67),
                    Producto(nombre='Latte vainilla', tipo='bebida', categoria='bebida', precio_cop=7500, precio_venta_cop=7500, precio_usd=2.08, precio_bs=1666.67),
                    Producto(nombre='Machiatto', tipo='bebida', categoria='bebida', precio_cop=5000, precio_venta_cop=5000, precio_usd=1.39, precio_bs=1111.11),
                    Producto(nombre='Merengadas (Fresa/Mora)', tipo='bebida', categoria='bebida', precio_cop=6000, precio_venta_cop=6000, precio_usd=1.67, precio_bs=1333.33),
                    Producto(nombre='Miel de abejas', tipo='bebida', categoria='bebida', precio_cop=10000, precio_venta_cop=10000, precio_usd=2.78, precio_bs=2222.22),
                    Producto(nombre='Mochaccino', tipo='bebida', categoria='bebida', precio_cop=7500, precio_venta_cop=7500, precio_usd=2.08, precio_bs=1666.67),
                    Producto(nombre='Refrescos', tipo='bebida', categoria='bebida', precio_cop=2500, precio_venta_cop=2500, precio_usd=0.69, precio_bs=555.56),
                    Producto(nombre='Taza o vaso de leche', tipo='bebida', categoria='bebida', precio_cop=3600, precio_venta_cop=3600, precio_usd=1.0, precio_bs=800.0),
                    Producto(nombre='Toddy caliente y frio', tipo='bebida', categoria='bebida', precio_cop=6500, precio_venta_cop=6500, precio_usd=1.81, precio_bs=1444.44),
                    # CERVEZAS (2)
                    Producto(nombre='Cerveza Polar', tipo='cerveza', categoria='cerveza', precio_cop=3600, precio_venta_cop=3600, precio_usd=1.0, precio_bs=800.0),
                    Producto(nombre='Malta Ret', tipo='cerveza', categoria='cerveza', precio_cop=2500, precio_venta_cop=2500, precio_usd=0.69, precio_bs=555.56),
                    # COMIDAS (3)
                    Producto(nombre='Ponquecito', tipo='comida', categoria='comida', precio_cop=2000, precio_venta_cop=2000, precio_usd=0.56, precio_bs=444.44),
                    Producto(nombre='Torta de chocolate', tipo='comida', categoria='comida', precio_cop=5000, precio_venta_cop=5000, precio_usd=1.39, precio_bs=1111.11),
                    Producto(nombre='Torta de vainilla', tipo='comida', categoria='comida', precio_cop=4000, precio_venta_cop=4000, precio_usd=1.11, precio_bs=888.89),
                    # GRANOS (3)
                    Producto(nombre='Kilo origen', tipo='grano', categoria='grano', precio_cop=72000, precio_venta_cop=72000, precio_usd=20.0, precio_bs=16000.0),
                    Producto(nombre='¼ Kilo origen', tipo='grano', categoria='grano', precio_cop=18000, precio_venta_cop=18000, precio_usd=5.0, precio_bs=4000.0),
                    Producto(nombre='½ Kilo origen', tipo='grano', categoria='grano', precio_cop=36000, precio_venta_cop=36000, precio_usd=10.0, precio_bs=8000.0),
                ]
                db.session.add_all(productos)
                db.session.commit()
                print("✔  32 productos del Excel creados (fallback).")
        else:
            print(f"ℹ️  Productos ya existen ({Producto.query.count()}) — omitido.")

        print()
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("  ¡Base de datos lista!      ")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"  Mesas:                 {Mesa.query.count()}")
        print(f"  Usuarios:              {Usuario.query.count()}")
        print(f"  Productos:             {Producto.query.count()}")
        print(f"  Tasas de cambio:       {TasaCambio.query.count()}")
        print(f"  Gastos registrados:    {Gasto.query.count()}")
        print()
        print("  Login: admin@caroai.com / admin123")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


if __name__ == '__main__':
    seed()
