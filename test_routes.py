"""
test_routes.py  —  Stability test for Caroai MVP (Fase 3, actualizado).

Adaptado al esquema actual:
  - Ubicacion → Mesa (Pedido.mesa_id)
  - POS es un blueprint propio (/pos/...) en vez de /sales/pos
  - La caja rápida es /sales/ (cart en sesión)
  - Se eliminó la sección /tables/ (el mapa de mesas es /pos/)
  - Void/restore viejos → anulación lógica vía /pos/pedido/<id>/anular
  - CSRF desactivado en config (no basta con el entorno en este proyecto)
  - Permisos: rol real del sistema es 'empleado' (no 'employee')

Uso:  python test_routes.py
"""

import os
import sys
import tempfile

os.chdir(os.path.dirname(os.path.abspath(__file__)))

TEST_DB = os.path.join(tempfile.gettempdir(), 'caroai_test.db')
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)

os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['DATABASE_URL'] = f'sqlite:///{TEST_DB}'
os.environ['WTF_CSRF_ENABLED'] = 'False'

from app import create_app
from app.models import (
    db, Usuario, Mesa, Producto, Insumo, TasaCambio, Gasto, Pedido,
)
from datetime import datetime, date

PASS = "✅  PASS"
FAIL = "❌  FAIL"

test_results = []
errors = []


def test(name, ok, detail=""):
    status = PASS if ok else FAIL
    test_results.append((status, name, detail))
    if not ok:
        errors.append(f"{FAIL} {name}: {detail or '?'}")
    print(f"  {status}  {name}" + (f"  — {detail}" if detail else ""))


def run_tests():
    app = create_app()
    # CSRFProtect lee la config en tiempo de request: desactivar en config, no solo en el entorno
    app.config['WTF_CSRF_ENABLED'] = False
    client = app.test_client()

    with app.app_context():
        db.create_all()

        # ── Seed usuarios (rol real del sistema: 'empleado') ──
        admin = Usuario(nombre='Admin Test', email='admin@test.com', rol='admin')
        admin.set_password('test123')
        emp = Usuario(nombre='Empleado Test', email='emp@test.com', rol='empleado')
        emp.set_password('test123')
        db.session.add_all([admin, emp])

        # ── Seed mesas ──
        mesas = [Mesa(nombre=f'Mesa {i}') for i in range(1, 7)] + [Mesa(nombre='Barra')]
        db.session.add_all(mesas)

        # ── Seed insumo + productos ──
        ins = Insumo(nombre='Café test kg', unidad_medida='kg',
                     costo_unitario_cop=72000, stock_actual=10, stock_minimo=2)
        db.session.add(ins)
        prod = Producto(nombre='Café Americano', tipo='bebida', categoria='bebida',
                        precio_cop=4500, precio_venta_cop=4500, descuenta_inventario=True)
        prod2 = Producto(nombre='Capuchino', tipo='bebida', categoria='bebida',
                         precio_cop=6500, precio_venta_cop=6500, descuenta_inventario=True)
        db.session.add_all([prod, prod2])

        # ── Seed tasa USD→COP (para POS/sales/reports) ──
        tasa = TasaCambio(moneda_origen='USD', moneda_destino='COP',
                          tasa=4200.0, vigente_desde=datetime.utcnow())
        db.session.add(tasa)
        db.session.commit()

        mesa1_id = mesas[0].id
        mesa2_id = mesas[1].id
        ins_id = ins.id
        prod_id = prod.id
        prod2_id = prod2.id

    def login(email):
        """Cambia de sesión. auth.login no cambia de usuario si ya hay sesión activa,
        así que se hace logout previo."""
        client.get('/auth/logout', follow_redirects=False)
        return client.post('/auth/login', data={
            'email': email,
            'password': 'test123',
        }, follow_redirects=False)

    def assert_ok(response, route_name):
        if response.status_code in (200, 302, 303):
            return True, ""
        if response.status_code == 500:
            return False, f"HTTP 500 on {route_name}"
        return False, f"HTTP {response.status_code} on {route_name}"

    print("\n" + "=" * 60)
    print("  CAROAI MVP — TEST DE ESTABILIDAD (Fase 3)")
    print("=" * 60)

    # ══════════════════════════════════════════════
    #  1. AUTH
    # ══════════════════════════════════════════════
    print("\n── Auth ──")

    resp = client.get('/auth/login')
    test("GET /auth/login", resp.status_code == 200)

    resp = client.post('/auth/login', data={'email': 'admin@test.com', 'password': 'test123'},
                       follow_redirects=False)
    test("POST login as admin", resp.status_code in (302, 303))

    client.get('/auth/logout', follow_redirects=False)
    resp = client.post('/auth/login', data={'email': 'admin@test.com', 'password': 'wrong'},
                       follow_redirects=True)
    test("Bad login stays on page", resp.status_code == 200)
    text = resp.data.decode()
    test("Bad login shows error message",
         'inválido' in text.lower() or 'incorrect' in text.lower() or 'intente' in text.lower())

    # ══════════════════════════════════════════════
    #  2. /tasas/ (admin only)
    # ══════════════════════════════════════════════
    print("\n── /tasas/ ──")

    login('admin@test.com')
    resp = client.get('/tasas/', follow_redirects=True)
    ok, msg = assert_ok(resp, '/tasas/')
    test("GET /tasas/ (admin) 200", ok, msg)
    test("  → shows USD/COP", 'USD' in resp.data.decode() and 'COP' in resp.data.decode())

    resp = client.get('/tasas/create')
    test("GET /tasas/create", resp.status_code == 200)

    resp = client.post('/tasas/create', data={
        'moneda_origen': 'USD', 'moneda_destino': 'VES', 'tasa': 100,
        'vigente_desde': '2026-07-01T00:00',
    }, follow_redirects=True)
    test("POST /tasas/create 200", resp.status_code == 200)

    with app.app_context():
        t = TasaCambio.query.filter_by(moneda_origen='USD', moneda_destino='VES').first()
        tasa_id = t.id if t else None
    if tasa_id:
        resp = client.get(f'/tasas/{tasa_id}/edit')
        test("GET /tasas/{id}/edit", resp.status_code == 200)

    # ══════════════════════════════════════════════
    #  3. POS (blueprint propio /pos/...)
    # ══════════════════════════════════════════════
    print("\n── POS /pos/ ──")

    login('admin@test.com')
    resp = client.get('/pos/', follow_redirects=True)
    ok, msg = assert_ok(resp, '/pos/')
    test("GET /pos/ (mapa) 200", ok, msg)
    test("  → shows Mesa 1", 'Mesa 1' in resp.data.decode())

    resp = client.post(f'/pos/{mesa1_id}/open', follow_redirects=False)
    test(f"POST /pos/{mesa1_id}/open → 302", resp.status_code in (302, 303))
    with app.app_context():
        m = db.session.get(Mesa, mesa1_id)
        test("  → mesa ocupada", m.estado == 'ocupada')

    resp = client.get(f'/pos/{mesa1_id}', follow_redirects=True)
    ok, msg = assert_ok(resp, f'/pos/{mesa1_id}')
    test(f"GET /pos/{mesa1_id} (POS mesa) 200", ok, msg)
    test("  → catálogo con Café Americano", 'Café Americano' in resp.data.decode())

    resp = client.post(f'/pos/{mesa1_id}/add', data={'producto_id': prod_id, 'cantidad': 2},
                       follow_redirects=False)
    test(f"POST /pos/{mesa1_id}/add → 302", resp.status_code in (302, 303))

    with app.app_context():
        po = Pedido.query.filter_by(mesa_id=mesa1_id, estado='abierto').first()
        test("  → item en pedido (cant 2)",
             po is not None and len(po.items) == 1 and po.items[0].cantidad == 2,
             f"items={len(po.items) if po else 0}")

    resp = client.post(f'/pos/{mesa1_id}/charge', data={
        'moneda_pago': 'COP', 'metodo_pago': 'efectivo',
    }, follow_redirects=False)
    test(f"POST /pos/{mesa1_id}/charge → 302", resp.status_code in (302, 303))

    pos_paid_id = None
    with app.app_context():
        p = Pedido.query.filter_by(mesa_id=mesa1_id, estado='pagado').first()
        test("  → pedido pagado (total 9000)",
             p is not None and p.total == 9000,
             f"total={p.total if p else None}")
        if p:
            pos_paid_id = p.id

    if pos_paid_id:
        resp = client.get(f'/pos/pedido/{pos_paid_id}', follow_redirects=True)
        ok, msg = assert_ok(resp, f'/pos/pedido/{pos_paid_id}')
        test(f"GET /pos/pedido/{pos_paid_id} 200", ok, msg)

    # ══════════════════════════════════════════════
    #  4. /sales/ (caja rápida, cart en sesión)
    # ══════════════════════════════════════════════
    print("\n── /sales/ ──")

    login('admin@test.com')
    resp = client.get('/sales/', follow_redirects=True)
    ok, msg = assert_ok(resp, '/sales/')
    test("GET /sales/ (caja) 200", ok, msg)

    resp = client.post('/sales/add', data={'producto_id': prod2_id, 'cantidad': 1},
                       follow_redirects=False)
    test("POST /sales/add → 302", resp.status_code in (302, 303))
    resp = client.get('/sales/', follow_redirects=True)
    ok, msg = assert_ok(resp, '/sales/ con cart')
    test("GET /sales/ (con cart) 200", ok, msg)
    with client.session_transaction() as sess:
        cart = sess.get('cart', [])
    test("  → carrito en sesión con Capuchino x1",
         len(cart) == 1 and cart[0]['producto_id'] == prod2_id and cart[0]['cantidad'] == 1,
         f"cart={cart}")

    resp = client.post('/sales/charge', data={
        'moneda_pago': 'COP', 'metodo_pago': 'efectivo',
    }, follow_redirects=False)
    test("POST /sales/charge → 302", resp.status_code in (302, 303))

    sales_paid_id = None
    with app.app_context():
        sp = Pedido.query.filter_by(estado='pagado').order_by(Pedido.id.desc()).first()
        if sp:
            sales_paid_id = sp.id

    resp = client.get('/sales/history', follow_redirects=True)
    ok, msg = assert_ok(resp, '/sales/history')
    test("GET /sales/history 200", ok, msg)

    if sales_paid_id:
        resp = client.get(f'/sales/{sales_paid_id}', follow_redirects=True)
        ok, msg = assert_ok(resp, f'/sales/{sales_paid_id}')
        test(f"GET /sales/{sales_paid_id} (detalle) 200", ok, msg)
        test("  → shows Capuchino", 'Capuchino' in resp.data.decode())

    # ══════════════════════════════════════════════
    #  5. /gastos/ (admin only)
    # ══════════════════════════════════════════════
    print("\n── /gastos/ ──")

    login('admin@test.com')
    resp = client.get('/gastos/', follow_redirects=True)
    ok, msg = assert_ok(resp, '/gastos/')
    test("GET /gastos/ (admin) 200", ok, msg)

    resp = client.get('/gastos/create')
    test("GET /gastos/create", resp.status_code == 200)

    hoy = date.today().isoformat()
    resp = client.post('/gastos/create', data={
        'concepto': 'Nuevo gasto test', 'categoria': 'insumos', 'monto': 50000,
        'moneda': 'COP', 'fecha': hoy,
    }, follow_redirects=True)
    test("POST /gastos/create 200", resp.status_code == 200)
    test("  → shows nuevo gasto", 'Nuevo gasto test' in resp.data.decode())

    with app.app_context():
        g = Gasto.query.filter_by(concepto='Nuevo gasto test').first()
        gasto_id = g.id if g else None
    if gasto_id:
        resp = client.get(f'/gastos/{gasto_id}/edit')
        test("GET /gastos/{id}/edit", resp.status_code == 200)
        resp = client.post(f'/gastos/{gasto_id}/delete', follow_redirects=True)
        test("POST /gastos/{id}/delete", resp.status_code == 200)

    # ══════════════════════════════════════════════
    #  6. /inventory/ (admin + empleado)
    # ══════════════════════════════════════════════
    print("\n── /inventory/ ──")

    login('admin@test.com')
    resp = client.get('/inventory/', follow_redirects=True)
    ok, msg = assert_ok(resp, '/inventory/')
    test("GET /inventory/ (admin) 200", ok, msg)
    test("  → shows insumo", 'Café test kg' in resp.data.decode())

    resp = client.get(f'/inventory/{ins_id}/movimientos', follow_redirects=True)
    ok, msg = assert_ok(resp, f'/inventory/{ins_id}/movimientos')
    test(f"GET /inventory/{ins_id}/movimientos 200", ok, msg)

    resp = client.get(f'/inventory/{ins_id}/movimiento/nuevo')
    test(f"GET /inventory/{ins_id}/movimiento/nuevo", resp.status_code == 200)

    resp = client.post(f'/inventory/{ins_id}/movimiento/nuevo', data={
        'tipo': 'entrada', 'cantidad': 5, 'motivo': 'Test compra',
    }, follow_redirects=True)
    test("POST nuevo movimiento (entrada)", resp.status_code == 200)
    with app.app_context():
        ins_check = db.session.get(Insumo, ins_id)
        test("  → stock actualizado 10+5=15",
             ins_check.stock_actual == 15,
             f"stock={ins_check.stock_actual}")

    # Empleado SÍ puede ver inventario y movimientos (fix de permisos)
    login('emp@test.com')
    resp = client.get('/inventory/', follow_redirects=True)
    ok, msg = assert_ok(resp, '/inventory/ (empleado)')
    test("GET /inventory/ (empleado) 200 ✓fix", ok, msg)

    resp = client.get(f'/inventory/{ins_id}/movimientos', follow_redirects=True)
    ok, msg = assert_ok(resp, f'/inventory/{ins_id}/movimientos (empleado)')
    test("GET /inventory/{id}/movimientos (empleado) 200 ✓fix", ok, msg)

    # ... pero NO puede crear insumos (admin only)
    resp = client.get('/inventory/create', follow_redirects=False)
    test("GET /inventory/create (empleado) → redirect", resp.status_code in (302, 303))

    # ══════════════════════════════════════════════
    #  7. /reports/ (diario: admin + empleado; mensual: admin)
    # ══════════════════════════════════════════════
    print("\n── /reports/ ──")

    login('admin@test.com')
    resp = client.get('/reports/', follow_redirects=True)
    ok, msg = assert_ok(resp, '/reports/')
    test("GET /reports/ (diario, admin) 200", ok, msg)

    resp = client.get('/reports/monthly', follow_redirects=True)
    ok, msg = assert_ok(resp, '/reports/monthly')
    test("GET /reports/monthly (admin) 200", ok, msg)

    # Empleado SÍ ve el reporte diario (fix de permisos), NO el mensual
    login('emp@test.com')
    resp = client.get('/reports/', follow_redirects=True)
    ok, msg = assert_ok(resp, '/reports/ (empleado)')
    test("GET /reports/ (empleado) 200 ✓fix", ok, msg)

    resp = client.get('/reports/monthly', follow_redirects=False)
    test("GET /reports/monthly (empleado) → redirect", resp.status_code in (302, 303))

    # ══════════════════════════════════════════════
    #  8. Empleado opera POS y caja (fix de permisos)
    # ══════════════════════════════════════════════
    print("\n── Empleado operando POS / Sales ──")

    login('emp@test.com')
    resp = client.get('/pos/', follow_redirects=True)
    ok, msg = assert_ok(resp, '/pos/ (empleado)')
    test("GET /pos/ (empleado) 200 ✓fix", ok, msg)

    resp = client.post(f'/pos/{mesa2_id}/open', follow_redirects=False)
    test(f"POST /pos/{mesa2_id}/open (empleado) → 302 ✓fix", resp.status_code in (302, 303))

    resp = client.post(f'/pos/{mesa2_id}/add', data={'producto_id': prod_id, 'cantidad': 1},
                       follow_redirects=False)
    test(f"POST /pos/{mesa2_id}/add (empleado) → 302 ✓fix", resp.status_code in (302, 303))

    resp = client.post(f'/pos/{mesa2_id}/charge', data={
        'moneda_pago': 'COP', 'metodo_pago': 'efectivo',
    }, follow_redirects=False)
    test(f"POST /pos/{mesa2_id}/charge (empleado) → 302 ✓fix", resp.status_code in (302, 303))

    resp = client.get('/sales/', follow_redirects=True)
    ok, msg = assert_ok(resp, '/sales/ (empleado)')
    test("GET /sales/ (empleado) 200 ✓fix", ok, msg)

    resp = client.get('/sales/history', follow_redirects=True)
    ok, msg = assert_ok(resp, '/sales/history (empleado)')
    test("GET /sales/history (empleado) 200 ✓fix", ok, msg)

    # Empleado bloqueado de módulos admin-only
    for path in ['/gastos/', '/tasas/', '/facturas/', '/notas/']:
        resp = client.get(path, follow_redirects=False)
        test(f"GET {path} (empleado) → redirect", resp.status_code in (302, 303))

    # ══════════════════════════════════════════════
    #  9. /notas/ (admin only)
    # ══════════════════════════════════════════════
    print("\n── /notas/ ──")

    login('admin@test.com')
    resp = client.get('/notas/', follow_redirects=True)
    ok, msg = assert_ok(resp, '/notas/')
    test("GET /notas/ (admin) 200", ok, msg)

    resp = client.post('/notas/nueva', data={
        'titulo': 'Recordatorio', 'tipo': 'general', 'contenido': 'x',
    }, follow_redirects=True)
    test("POST /notas/nueva 200", resp.status_code == 200)
    test("  → nota visible", 'Recordatorio' in resp.data.decode())

    # ══════════════════════════════════════════════
    #  10. Anulación lógica (admin only)
    # ══════════════════════════════════════════════
    print("\n── Anulación /pos/pedido ──")

    login('admin@test.com')
    if pos_paid_id:
        resp = client.post(f'/pos/pedido/{pos_paid_id}/anular',
                           data={'motivo': 'Test anulación'}, follow_redirects=False)
        test(f"POST /pos/pedido/{pos_paid_id}/anular → 302", resp.status_code in (302, 303))
        with app.app_context():
            pp = db.session.get(Pedido, pos_paid_id)
            test("  → pedido estado = anulado", pp.estado == 'anulado', f"estado={pp.estado}")
            test("  → items anulados lógicamente",
                 all(i.anulado for i in pp.items))

        login('emp@test.com')
        resp = client.post(f'/pos/pedido/{pos_paid_id}/anular',
                           data={'motivo': 'x'}, follow_redirects=False)
        test("POST anular (empleado) → redirect", resp.status_code in (302, 303))

    # ══════════════════════════════════════════════
    #  11. Comparación de meses (/reports/compare)
    # ══════════════════════════════════════════════
    print("\n── Comparación de meses ──")

    # En este punto hay 3 pedidos del mes actual: uno anulado (excluido) y 2 pagados
    # (6500 caja + 4500 POS empleado = 11000 COP).
    hoy_cmp = date.today()
    mes_actual, anio_actual = hoy_cmp.month, hoy_cmp.year
    if mes_actual == 1:
        mes_anterior, anio_anterior = 12, anio_actual - 1
    else:
        mes_anterior, anio_anterior = mes_actual - 1, anio_actual

    from app.routes.reports import _resumen_mes
    with app.app_context():
        ra = _resumen_mes(mes_actual, anio_actual)
        rb = _resumen_mes(mes_anterior, anio_anterior)
    test("Resumen mes actual: 2 pedidos pagados (anulado excluido)",
         ra['num_pedidos'] == 2 and ra['total_vendido_cop'] == 11000,
         f"pedidos={ra['num_pedidos']}, total={ra['total_vendido_cop']}")
    test("Resumen mes anterior: sin datos",
         rb['num_pedidos'] == 0 and rb['total_vendido_cop'] == 0)

    login('admin@test.com')
    resp = client.get('/reports/compare', follow_redirects=True)
    ok, msg = assert_ok(resp, '/reports/compare')
    test("GET /reports/compare (admin) 200", ok, msg)
    test("  → muestra Mes A / Mes B",
         'Mes A' in resp.data.decode() and 'Mes B' in resp.data.decode())

    resp = client.get(
        f'/reports/compare?mes_a={mes_actual}&anio_a={anio_actual}'
        f'&mes_b={mes_anterior}&anio_b={anio_anterior}',
        follow_redirects=True)
    ok, msg = assert_ok(resp, '/reports/compare (params)')
    test("GET /reports/compare (params) 200", ok, msg)
    test("  → tabla con total vendido", 'Total vendido' in resp.data.decode())

    login('emp@test.com')
    resp = client.get('/reports/compare', follow_redirects=False)
    test("GET /reports/compare (empleado) → redirect", resp.status_code in (302, 303))

    # ══════════════════════════════════════════════
    #  12. Conversión de monedas (currency.py)
    # ══════════════════════════════════════════════
    print("\n── Conversión de monedas ──")

    from app.utils.currency import convertir_cop_a
    with app.app_context():
        m, t, err = convertir_cop_a(42000, 'COP')
        test("COP→COP sin cambio",
             m == 42000 and t == 1.0 and err is None, f"{m}, {t}, {err}")
        # Tasa seedeada al inicio: 1 USD = 4200 COP
        m, t, err = convertir_cop_a(42000, 'USD')
        test("COP→USD con tasa guardada (4200)",
             m == 10.0 and t == 4200.0 and err is None, f"{m}, {t}, {err}")
        m, t, err = convertir_cop_a(100, 'XXX')
        test("Moneda no soportada → error",
             m is None and t is None and err is not None, f"{err}")

    # ══════════════════════════════════════════════
    #  SUMMARY
    # ══════════════════════════════════════════════
    passed = sum(1 for s, _, _ in test_results if s == PASS)
    failed_count = sum(1 for s, _, _ in test_results if s == FAIL)
    total = len(test_results)

    print("\n" + "=" * 60)
    print(f"  RESULTADOS: {passed}/{total} pasaron  ({failed_count} fallaron)")
    print("=" * 60)

    if errors:
        print("\n  Fallos:")
        for e in errors:
            print(f"    {e}")

    print()
    return failed_count == 0


if __name__ == '__main__':
    success = run_tests()
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    sys.exit(0 if success else 1)
