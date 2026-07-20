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
        # Formato: { 'tabla': [ (col, tipo_sql, es_fk, ref_table, ref_col), ... ] }
        #   es_fk=True significa: agregar como NULL, luego NOT NULL, y crear FK en Postgres
        column_fixes = [
            # (tabla, col, tipo_sql, es_fk, ref_table, ref_col, default_val)
            ('pedidos', 'mesa_id', 'INTEGER', True, 'mesas', 'id', 1),
            ('pedidos', 'moneda_pago', 'VARCHAR(10)', False, None, None, None),
            ('pedidos', 'metodo_pago', 'VARCHAR(20)', False, None, None, None),
            ('pedidos', 'tasa_aplicada', 'FLOAT', False, None, None, None),
            ('pedidos', 'total_pagado_moneda', 'FLOAT', False, None, None, None),
            ('pedidos', 'observaciones', 'VARCHAR(300)', False, None, None, None),
            ('pedido_items', 'anulado_en', 'TIMESTAMP', False, None, None, None),
            ('pedido_items', 'motivo_anulacion', 'VARCHAR(200)', False, None, None, None),
            ('productos', 'precio_usd', 'FLOAT', False, None, None, None),
            ('productos', 'precio_bs', 'FLOAT', False, None, None, None),
            ('productos', 'precio_venta_cop', 'INTEGER', False, None, None, 0),
            ('productos', 'descuenta_inventario', 'BOOLEAN', False, None, None, False),
            ('productos', 'insumo_id', 'INTEGER', False, None, None, None),
        ]

        for table, col_name, col_type, es_fk, ref_table, ref_col, default_val in column_fixes:
            if table in tables:
                existing = {c['name'] for c in insp.get_columns(table)}
                if col_name not in existing:
                    if engine_name == 'postgresql' and es_fk:
                        # FK columns: add as NULL first, fill default, then NOT NULL + FK
                        print(f'  → Agregando {table}.{col_name} como NULLABLE (FK pendiente)...')
                        db.session.execute(text(
                            f'ALTER TABLE {table} ADD COLUMN {col_name} {col_type} NULL'
                        ))
                        db.session.commit()
                        print(f'    → Asignando valor por defecto ({default_val}) a filas existentes...')
                        db.session.execute(text(
                            f'UPDATE {table} SET {col_name} = {default_val} WHERE {col_name} IS NULL'
                        ))
                        db.session.commit()
                        print(f'    → Estableciendo NOT NULL...')
                        db.session.execute(text(
                            f'ALTER TABLE {table} ALTER COLUMN {col_name} SET NOT NULL'
                        ))
                        db.session.commit()
                        # Verificar que la tabla referenciada tenga datos
                        ref_count = db.session.execute(text(
                            f'SELECT COUNT(*) FROM {ref_table}'
                        )).scalar()
                        if ref_count == 0:
                            print(f'    ⚠️  Tabla {ref_table} vacía — insertando datos por defecto...')
                            if ref_table == 'mesas':
                                nombres = ['Mesa 1','Mesa 2','Mesa 3','Mesa 4','Mesa 5','Mesa 6','Barra']
                                for i, n in enumerate(nombres):
                                    db.session.execute(text(
                                        f"INSERT INTO {ref_table} (id, nombre, estado) VALUES ({i+1}, '{n}', 'libre')"
                                    ))
                                db.session.commit()
                                print(f'    ✅ 7 mesas creadas (Mesa 1-6 + Barra).')
                        print(f'    → Agregando FK {table}.{col_name} → {ref_table}.{ref_col}...')
                        fk_name = f'fk_{table}_{col_name}'
                        try:
                            db.session.execute(text(
                                f'ALTER TABLE {table} ADD CONSTRAINT {fk_name} '
                                f'FOREIGN KEY ({col_name}) REFERENCES {ref_table}({ref_col})'
                            ))
                            db.session.commit()
                            print(f'  ✅ {table}.{col_name} agregada con FK a {ref_table}.{ref_col}.')
                        except Exception as e:
                            db.session.rollback()
                            print(f'  ⚠️ FK {fk_name}: {e} (la columna ya existe sin constraint, puede agregarse manualmente después)')
                    elif engine_name == 'postgresql':
                        # Columnas regulares: nullable logic
                        nullable = 'NULL'
                        default = ''
                        if default_val is not None:
                            # Has default value
                            if col_name == 'descuenta_inventario':
                                default = ' DEFAULT FALSE'
                                nullable = 'NOT NULL'
                            elif col_name == 'precio_venta_cop':
                                default = ' DEFAULT 0'
                                nullable = 'NOT NULL'
                            else:
                                nullable = 'NULL'
                        else:
                            nullable = 'NULL'
                        sql = f'ALTER TABLE {table} ADD COLUMN {col_name} {col_type} {nullable}{default}'
                        try:
                            db.session.execute(text(sql))
                            db.session.commit()
                            print(f'  ✅ {table}.{col_name} agregada.')
                        except Exception as e:
                            db.session.rollback()
                            print(f'  ⚠️ {table}.{col_name}: {e}')
                    else:
                        # SQLite
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
        #  3. Sembrar mesas por defecto si la tabla está vacía
        #     (independientemente de si mesa_id ya existe o no)
        # ──────────────────────────────────────────────
        print()
        print('🏗️  Verificando datos iniciales...')
        if 'mesas' in tables:
            count = db.session.execute(text('SELECT COUNT(*) FROM mesas')).scalar()
            if count == 0:
                print('  → Sembrando 7 mesas por defecto (Mesa 1-6 + Barra)...')
                nombres = ['Mesa 1','Mesa 2','Mesa 3','Mesa 4','Mesa 5','Mesa 6','Barra']
                for i, n in enumerate(nombres):
                    db.session.execute(text(
                        f"INSERT INTO mesas (id, nombre, estado) VALUES ({i+1}, '{n}', 'libre')"
                    ))
                db.session.commit()
                print('  ✅ 7 mesas creadas.')
            else:
                print(f'  ✅ {count} mesas ya existen — omitido.')
        else:
            print('  ℹ️  Tabla mesas no existe (se creará con create_all).')

        if 'usuarios' in tables:
            count = db.session.execute(text('SELECT COUNT(*) FROM usuarios')).scalar()
            if count == 0:
                print('  → No hay usuarios registrados. Crea uno con: flask create-admin')
            else:
                print(f'  ✅ {count} usuarios ya existen.')

        # ──────────────────────────────────────────────
        #  4. Crear tablas completamente nuevas
        # ──────────────────────────────────────────────
        print()
        print('🏗️  Ejecutando db.create_all() para tablas nuevas...')
        db.create_all()
        print('  ✅ create_all() completado.')

        # ──────────────────────────────────────────────
        #  5. Verificación final
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
