"""
seed_data.py  —  Inicializa la base de datos con datos de prueba completos (Fase 4).

Uso:  python seed_data.py

Construye una app Flask mínima (solo DB, sin rutas).
Elimina todas las tablas y las recrea con datos de prueba.
"""

from flask import Flask
from app.models import (
    db, Usuario, Ubicacion, Producto, Insumo,
    Receta, TasaCambio, Gasto,
)
from datetime import datetime, date


def _minimal_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'seed-only'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///caroai.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app


def seed():
    app = _minimal_app()

    with app.app_context():
        db.drop_all()
        db.create_all()
        print("✔  Tablas recreadas desde cero.")

        # ────────────────────────────────────────
        #  1. USUARIOS
        # ────────────────────────────────────────
        admin = Usuario(nombre='Admin Caroai', email='admin@caroai.com', rol='admin')
        admin.set_password('admin123')

        empleado = Usuario(nombre='Empleado Caroai', email='empleado@caroai.com', rol='empleado')
        empleado.set_password('empleado123')

        db.session.add_all([admin, empleado])
        db.session.commit()
        print("✔  Usuarios: admin@caroai.com / empleado@caroai.com")

        # ────────────────────────────────────────
        #  2. UBICACIONES
        # ────────────────────────────────────────
        ubicaciones = [
            Ubicacion(nombre='Mesa 1', tipo='mesa'),
            Ubicacion(nombre='Mesa 2', tipo='mesa'),
            Ubicacion(nombre='Mesa 3', tipo='mesa'),
            Ubicacion(nombre='Mesa 4', tipo='mesa'),
            Ubicacion(nombre='Mesa 5', tipo='mesa'),
            Ubicacion(nombre='Mesa 6', tipo='mesa'),
            Ubicacion(nombre='Barra', tipo='barra'),
            Ubicacion(nombre='Puff 1', tipo='puff'),
            Ubicacion(nombre='Puff 2', tipo='puff'),
        ]
        db.session.add_all(ubicaciones)
        db.session.commit()
        print("✔  9 ubicaciones (6 mesas + 1 barra + 2 puffs)")

        # ────────────────────────────────────────
        #  3. INSUMOS
        # ────────────────────────────────────────
        insumos = [
            Insumo(nombre='Café en grano x kg',       unidad_medida='kg',    costo_unitario_cop=72000, stock_actual=10, stock_minimo=2),
            Insumo(nombre='Leche entera x 900ml',     unidad_medida='l',     costo_unitario_cop=3000,  stock_actual=15, stock_minimo=5),
            Insumo(nombre='Refresco lata x 355ml',    unidad_medida='unidad', costo_unitario_cop=1800,  stock_actual=48, stock_minimo=12),
            Insumo(nombre='Pastel entero x 10 porc',  unidad_medida='unidad', costo_unitario_cop=25000, stock_actual=4,  stock_minimo=1),
        ]
        db.session.add_all(insumos)
        db.session.commit()

        insumo_cafe = Insumo.query.filter_by(nombre='Café en grano x kg').first()
        insumo_leche = Insumo.query.filter_by(nombre='Leche entera x 900ml').first()
        insumo_refresco = Insumo.query.filter_by(nombre='Refresco lata x 355ml').first()
        insumo_pastel = Insumo.query.filter_by(nombre='Pastel entero x 10 porc').first()
        print("✔  4 insumos base con stock inicial")

        # ────────────────────────────────────────
        #  4. PRODUCTOS
        # ────────────────────────────────────────
        productos = [
            Producto(
                nombre='Café Americano',
                categoria='bebida',
                precio_venta_cop=4500,
                descuenta_inventario=True,  # ahora SÍ descuenta via Receta
            ),
            Producto(
                nombre='Capuchino',
                categoria='bebida',
                precio_venta_cop=6500,
                descuenta_inventario=True,  # ahora SÍ descuenta via Receta
            ),
            Producto(
                nombre='Refresco Personal',
                categoria='bebida',
                precio_venta_cop=3000,
                descuenta_inventario=True,
                insumo_id=insumo_refresco.id,  # fallback directo (sin receta)
            ),
            Producto(
                nombre='Porción de Torta',
                categoria='comida',
                precio_venta_cop=5000,
                descuenta_inventario=True,
                insumo_id=insumo_pastel.id,  # fallback directo (sin receta)
            ),
        ]
        db.session.add_all(productos)
        db.session.commit()

        prod_cafe = Producto.query.filter_by(nombre='Café Americano').first()
        prod_capuchino = Producto.query.filter_by(nombre='Capuchino').first()
        print("✔  4 productos (Café Americano y Capuchino con descuenta_inventario=True)")

        # ────────────────────────────────────────
        #  5. RECETAS (Fase 4)
        # ────────────────────────────────────────
        recetas = [
            Receta(
                producto_id=prod_cafe.id,
                insumo_id=insumo_cafe.id,
                cantidad_gramos=18.0,  # 18g de café por taza de Americano
                descripcion='base',
            ),
            Receta(
                producto_id=prod_capuchino.id,
                insumo_id=insumo_cafe.id,
                cantidad_gramos=18.0,  # 18g de café
                descripcion='base',
            ),
            Receta(
                producto_id=prod_capuchino.id,
                insumo_id=insumo_leche.id,
                cantidad_gramos=200.0,  # 200ml de leche (≈200g para descuento)
                descripcion='leche vaporizada',
            ),
        ]
        db.session.add_all(recetas)
        db.session.commit()
        print("✔  3 recetas:")
        print("      Café Americano → 18g Café en grano")
        print("      Capuchino → 18g Café en grano + 200g Leche")

        # ────────────────────────────────────────
        #  6. TASAS DE CAMBIO (Fase 4)
        # ────────────────────────────────────────
        tasas = [
            TasaCambio(
                moneda_origen='COP',
                moneda_destino='USD',
                tasa=4200.0,
                vigente_desde=datetime(2026, 7, 1, 0, 0, 0),
            ),
            TasaCambio(
                moneda_origen='COP',
                moneda_destino='VES',
                tasa=0.18,  # 1 COP = 0.18 VES (tasa de referencia)
                vigente_desde=datetime(2026, 7, 1, 0, 0, 0),
            ),
        ]
        db.session.add_all(tasas)
        db.session.commit()
        print("✔  2 tasas de cambio:")
        print("      1 COP = 0.000238 USD")
        print("      1 COP = 0.18 VES")

        # ────────────────────────────────────────
        #  7. GASTOS DE EJEMPLO (Fase 3)
        # ────────────────────────────────────────
        gastos = [
            Gasto(
                concepto='Pago nómina mes julio',
                categoria='nomina',
                monto=2400000,
                moneda='COP',
                fecha=date(2026, 7, 15),
            ),
            Gasto(
                concepto='Compra leche fresca Alpina',
                categoria='insumos',
                monto=45000,
                moneda='COP',
                fecha=date(2026, 7, 10),
                observaciones='15 unidades x 900ml',
            ),
            Gasto(
                concepto='Reparación máquina espresso',
                categoria='mantenimiento',
                monto=180000,
                moneda='COP',
                fecha=date(2026, 7, 8),
            ),
            Gasto(
                concepto='Pago factura internet',
                categoria='mantenimiento',
                monto=35,
                moneda='USD',
                fecha=date(2026, 7, 5),
                observaciones='Pago mensual proveedor',
            ),
        ]
        db.session.add_all(gastos)
        db.session.commit()
        print("✔  4 gastos de ejemplo (nómina, insumos, mantenimiento COP y USD)")

        # ────────────────────────────────────────
        #  RESUMEN
        # ────────────────────────────────────────
        insumo_cafe = Insumo.query.filter_by(nombre='Café en grano x kg').first()
        insumo_leche = Insumo.query.filter_by(nombre='Leche entera x 900ml').first()
        # Simular 10 ventas de café para probar descuento
        # (el stock inicial se descuenta al vender, no en seed)

        print()
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("  ¡Base de datos Fase 4 lista!")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"  Stock Café en grano:  {insumo_cafe.stock_actual} kg")
        print(f"  Stock Leche:          {insumo_leche.stock_actual} l")
        print(f"  Recetas activas:      {Receta.query.count()}")
        print(f"  Tasas de cambio:      {TasaCambio.query.count()}")
        print(f"  Gastos registrados:   {Gasto.query.count()}")
        print()
        print("  Prueba rápida:")
        print("  1. python run.py")
        print("  2. Login como admin@caroai.com / admin123")
        print("  3. Abrir una mesa, crear pedido con Café Americano")
        print("  4. Cobrar y verificar que se descuentan 18g de café en grano")
        print("  5. Ir a Recetas → ver las 3 recetas creadas")
        print("  6. Ir a Tasas → ver las 2 tasas de cambio")
        print("  7. Ir a Reportes → Mensual → ver balance unificado estimado en USD")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


if __name__ == '__main__':
    seed()
