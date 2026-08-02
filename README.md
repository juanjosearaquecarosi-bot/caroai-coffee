# Caroai Café Control

Aplicación interna de gestión para el café: control de mesas y caja, inventario, gastos, tasas de cambio, facturas, notas y reportes.

## Funcionalidad

- **POS por mesas**: mapa de mesas, abrir mesa, agregar/quitar productos, cargos manuales, cobrar en COP/USD/VES y marcar pendiente.
- **Caja rápida**: venta directa sin mesa con carrito en sesión.
- **Inventario**: insumos, stock mínimo/máximo y movimientos (entrada / salida / merma / ajuste).
- **Gastos**: registro y filtros por mes/año/categoría, con edición y borrado.
- **Tasas de cambio**: tasas de referencia para conversión de monedas (directas y Táchira/compra/venta).
- **Facturas**: control de cuentas por pagar con vencimientos.
- **Notas**: notas generales y cuentas por cobrar (deudas).
- **Reportes**: diario, mensual y comparación entre dos meses (con datos guardados del cobro).
- **Autenticación**: login con roles `admin` / `empleado`. Admin gestiona módulos administrativos; el empleado opera POS, caja, inventario y reportes diarios.

## Setup

1. Instalar dependencias:
   ```bash
   pip install -r requirements.txt
   ```
2. Sembrar datos iniciales:
   ```bash
   python seed_data.py
   ```
3. Ejecutar:
   ```bash
   python run.py
   ```
4. Abrir `http://localhost:5000`. Usuarios de seed: `admin@caroai.com` / `empleado@caroai.com` (ver seed_data.py para contraseñas).

## Tests

Smoke test de estabilidad de rutas y permisos (SQLite temporal):

```bash
python test_routes.py
```

## Estructura

```
/app
   __init__.py    # app factory + blueprints
   models.py      # modelos SQLAlchemy
   database.py    # inicialización de la BD
   routes/        # auth, pos, sales, inventory, gastos, tasas, facturas, notas, reports
   utils/         # decorators (roles), currency (conversión), excel_import
   templates/     # plantillas por módulo
seed_data.py      # datos iniciales
migrate_db.py     # migración de esquema para Postgres (Render)
test_routes.py    # smoke tests
run.py            # entry point de desarrollo
wsgi.py           # entry point para gunicorn
```

## Notas

- SQLite por defecto (`instance/caroai.db`); en Render se usa Postgres vía `DATABASE_URL` y se ejecuta `migrate_db.py` en el release.
- El control fiscal (SENIAT/QUORiON) está fuera de alcance.
- Los reportes de comparación usan los montos y tasas guardados en el momento del cobro; no recalculan ventas pasadas con tasas nuevas.
