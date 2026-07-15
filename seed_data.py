from app import create_app
from app.models import db, Producto, Insumo, TasaCambio, Receta
from datetime import date
import os

def seed_data():
    app = create_app()
    with app.app_context():
        # Create tables if they don't exist
        db.create_all()

        # Seed inicial data from Excel (we'll use sample data for now)
        excel_path = os.path.join(os.path.dirname(__file__), '..', '..', 'Descargas', 'Caroai Cafe control ventas (1).xlsx')
        if os.path.exists(excel_path):
            print("Parsing Excel file...")
            # For now, we'll skip parsing and manually insert some sample data.
            # In a real scenario, we would call parse_excel and insert.
            # We'll insert a few sample productos and insumos to test.
            pass
        else:
            print("Excel file not found, using sample data.")

        # Check if we already have data
        if Producto.query.count() == 0:
            # Sample products
            productos_sample = [
                {'nombre': 'Espresso', 'categoria': 'bebida', 'precio_venta_cop': 4000},
                {'nombre': 'Americano', 'categoria': 'bebida', 'precio_venta_cop': 4500},
                {'nombre': 'Cappuccino', 'categoria': 'bebida', 'precio_venta_cop': 6500},
                {'nombre': 'Latte', 'categoria': 'bebida', 'precio_venta_cop': 7500},
                {'nombre': 'Torta de chocolate', 'categoria': 'comida', 'precio_venta_cop': 5000},
                {'nombre': 'Empanada', 'categoria': 'comida', 'precio_venta_cop': 3000},
            ]
            for p in productos_sample:
                producto = Producto(**p)
                db.session.add(producto)
            db.session.commit()
            print(f"Added {len(productos_sample)} sample products.")

        if Insumo.query.count() == 0:
            # Sample insumos
            insumos_sample = [
                {'nombre': 'Café kilo', 'unidad_medida': 'kg', 'costo_unitario_cop': 72000, 'stock_actual': 10, 'stock_minimo': 2},
                {'nombre': 'Leche 900ml', 'unidad_medida': 'l', 'costo_unitario_cop': 3000, 'stock_actual': 20, 'stock_minimo': 5},
                {'nombre': 'Azucar 100 sticks', 'unidad_medida': 'unidad', 'costo_unitario_cop': 10000, 'stock_actual': 50, 'stock_minimo': 10},
                {'nombre': 'Cacao kilo', 'unidad_medida': 'kg', 'costo_unitario_cop': 20000, 'stock_actual': 5, 'stock_minimo': 1},
                {'nombre': 'Vainilla litro', 'unidad_medida': 'l', 'costo_unitario_cop': 8000, 'stock_actual': 10, 'stock_minimo': 2},
            ]
            for insumo in insumos_sample:
                i = Insumo(**insumo)
                db.session.add(i)
            db.session.commit()
            print(f"Added {len(insumos_sample)} sample insumos.")

        # Ensure we have a tasa for today
        today = date.today()
        if not TasaCambio.query.filter_by(fecha=today).first():
            tasa = TasaCambio(
                fecha=today,
                tasa_cop_usd=3600.0,   # placeholder, should be configured
                tasa_tienda_bs_usd=4.5   # placeholder
            )
            db.session.add(tasa)
            db.session.commit()
            print(f"Added tasa for {today}")

        # Add sample recetas (producto -> insumo)
        if Receta.query.count() == 0:
            # We need to get the producto and insumo ids
            espresso = Producto.query.filter_by(nombre='Espresso').first()
            cappuccino = Producto.query.filter_by(nombre='Cappuccino').first()
            latte = Producto.query.filter_by(nombre='Latte').first()
            torta_chocolate = Producto.query.filter_by(nombre='Torta de chocolate').first()

            cafe_kilo = Insumo.query.filter_by(nombre='Café kilo').first()
            leche_900ml = Insumo.query.filter_by(nombre='Leche 900ml').first()
            azucar_sticks = Insumo.query.filter_by(nombre='Azucar 100 sticks').first()
            cacao_kilo = Insumo.query.filter_by(nombre='Cacao kilo').first()
            vainilla_litro = Insumo.query.filter_by(nombre='Vainilla litro').first()

            recetas_sample = [
                # Espresso: 18g de café por taza (0.018 kg)
                {'producto_id': espresso.id, 'insumo_id': cafe_kilo.id, 'cantidad_usada_por_unidad': 0.018},
                # Cappuccino: mismo café + leche
                {'producto_id': cappuccino.id, 'insumo_id': cafe_kilo.id, 'cantidad_usada_por_unidad': 0.018},
                {'producto_id': cappuccino.id, 'insumo_id': leche_900ml.id, 'cantidad_usada_por_unidad': 0.15},  # 150 ml
                # Latte: más leche
                {'producto_id': latte.id, 'insumo_id': cafe_kilo.id, 'cantidad_usada_por_unidad': 0.018},
                {'producto_id': latte.id, 'insumo_id': leche_900ml.id, 'cantidad_usada_por_unidad': 0.25},  # 250 ml
                # Torta de chocolate: harina, cacao, etc. We'll simplified: cacao
                {'producto_id': torta_chocolate.id, 'insumo_id': cacao_kilo.id, 'cantidad_usada_por_unidad': 0.05},  # 50g per unidad
                # Azúcar para bebidas (opcional)
                {'producto_id': espresso.id, 'insumo_id': azucar_sticks.id, 'cantidad_usada_por_unidad': 1},  # 1 stick
                {'producto_id': cappuccino.id, 'insumo_id': azucar_sticks.id, 'cantidad_usada_por_unidad': 1},
                {'producto_id': latte.id, 'insumo_id': azucar_sticks.id, 'cantidad_usada_por_unidad': 1},
            ]
            for r in recetas_sample:
                receta = Receta(**r)
                db.session.add(receta)
            db.session.commit()
            print(f"Added {len(recetas_sample)} sample recetas.")

if __name__ == '__main__':
    seed_data()
    print("Seeding completed.")