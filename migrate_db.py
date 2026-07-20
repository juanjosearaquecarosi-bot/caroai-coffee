"""
migrate_db.py  —  Migración de esquema para Render (Postgres).

Uso:
    python migrate_db.py

Corrige:
  - mesas.numero → mesas.nombre
  - Columnas faltantes en tablas existentes
  - Crea tablas faltantes con db.create_all()

Requiere variable de entorno DATABASE_URL (Render la inyecta automáticamente).
"""

import os
import sys

os.environ.setdefault('FLASK_APP', 'app')

from app import create_app
from app.models import db
from sqlalchemy import inspect, text

app = create_app()

if __name__ == '__main__':
    with app.app_context():
        insp = inspect(db.engine)
        tables = insp.get_table_names()
        engine_name = db.engine.name
        print(f'🔧 Motor: {engine_name}')
        print(f'📋 Tablas existentes ({len(tables)}): {", ".join(sorted(tables))}')
        print()

        # ──────────────────────────────────────────────
        #  1. Migrar mesas: numero → nombre
        # ──────────────────────────────────────────────
        if 'mesas' in tables:
            cols = [c['name'] for c in insp.get_columns('mesas')]
            print(f'📌 Columnas en mesas: {cols}')

            if 'numero' in cols and 'nombre' not in cols:
                print('  → Renombrando mesas.numero → mesas.nombre ...')
                db.session.execute(text(
                    'ALTER TABLE mesas RENAME COLUMN numero TO nombre'
                ))
                db.session.commit()
                print('  ✅ Renombrado correctamente.')
            elif 'nombre' in cols:
                print('  ✅ mesas.nombre ya existe — no requiere migración.')
            else:
                print('  ⚠️ No se encontró ni numero ni nombre en mesas.')
        else:
            print('⚠️ Tabla mesas no existe — será creada por create_all().')

        # ──────────────────────────────────────────────
        #  2. Agregar columnas faltantes en tablas existentes
        #     (create_all() NO agrega columnas nuevas a tablas existentes)
        # ──────────────────────────────────────────────
        print()
        print('🔧 Agregando columnas faltantes en tablas existentes...')

        # Columnas que podrían no existir en schemas antiguos
        # Formato: { 'tabla': [ (col, tipo_sql), ... ] }
        column_fixes = {
            'pedidos': [
                ('moneda_pago', 'VARCHAR(10)'),
                ('metodo_pago', 'VARCHAR(20)'),
                ('observaciones', 'VARCHAR(300)'),
            ],
            'pedido_items': [
                ('anulado_en', 'TIMESTAMP'),
                ('motivo_anulacion', 'VARCHAR(200)'),
            ],
            'productos': [
                ('precio_usd', 'FLOAT'),
                ('precio_bs', 'FLOAT'),
                ('precio_venta_cop', 'INTEGER'),
                ('descuenta_inventario', 'BOOLEAN'),
                ('insumo_id', 'INTEGER'),
            ],
        }

        for table, columns in column_fixes.items():
            if table in tables:
                existing = {c['name'] for c in insp.get_columns(table)}
                for col_name, col_type in columns:
                    if col_name not in existing:
                        if engine_name == 'postgresql':
                            # Verificar si es FK o tiene default
                            nullable = 'NULL' if col_name == 'insumo_id' else 'NOT NULL'
                            default = ''
                            if col_name == 'descuenta_inventario':
                                default = ' DEFAULT FALSE'
                            elif col_name == 'precio_venta_cop':
                                default = ' DEFAULT 0'
                            sql = f'ALTER TABLE {table} ADD COLUMN {col_name} {col_type} {nullable}{default}'
                        else:
                            # SQLite no soporta ADD COLUMN con NOT NULL sin default
                            sql = f'ALTER TABLE {table} ADD COLUMN {col_name} {col_type}'
                        try:
                            db.session.execute(text(sql))
                            db.session.commit()
                            print(f'  ✅ {table}.{col_name} agregada.')
                        except Exception as e:
                            db.session.rollback()
                            print(f'  ⚠️ {table}.{col_name}: {e}')
                    else:
                        print(f'  ✅ {table}.{col_name} ya existe.')
            else:
                print(f'  ℹ️  Tabla {table} no existe (se creará con create_all).')

        # ──────────────────────────────────────────────
        #  3. Crear tablas completamente nuevas
        # ──────────────────────────────────────────────
        print()
        print('🏗️  Ejecutando db.create_all() para tablas nuevas...')
        db.create_all()
        print('  ✅ create_all() completado.')

        # ──────────────────────────────────────────────
        #  4. Verificación final
        # ──────────────────────────────────────────────
        print()
        tables_post = insp.get_table_names()
        print(f'📊 Tablas después de migración ({len(tables_post)}):')
        for t in sorted(tables_post):
            n_cols = len(insp.get_columns(t))
            print(f'  · {t} ({n_cols} columnas)')

        print()
        print('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
        print('  ✅ Migración completada.')
        print('  Próximo paso: reiniciar el servicio en Render.')
        print('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
