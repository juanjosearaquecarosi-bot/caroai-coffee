"""
test_routes.py  —  Comprehensive stability test for Caroai MVP.
Tests all major routes with real Flask test_client using file-based SQLite.
"""

import os
import sys
import traceback
import tempfile

os.chdir(os.path.dirname(os.path.abspath(__file__)))

TEST_DB = os.path.join(tempfile.gettempdir(), 'caroai_test.db')
# Remove if exists
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)

os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['DATABASE_URL'] = f'sqlite:///{TEST_DB}'
os.environ['WTF_CSRF_ENABLED'] = 'False'

from app import create_app
from app.models import db, Usuario, Ubicacion, Producto, Insumo, TasaCambio, Gasto, Pedido, PedidoItem
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
    client = app.test_client()

    with app.app_context():
        db.create_all()

        # ── Seed test users ──
        admin = Usuario(nombre='Admin Test', email='admin@test.com', rol='admin')
        admin.set_password('test123')
        emp = Usuario(nombre='Employee Test', email='emp@test.com', rol='empleado')
        emp.set_password('test123')
        db.session.add_all([admin, emp])
        db.session.commit()

        admin_id = admin.id
        emp_id = emp.id

    def login(email, password):
        return client.post('/auth/login', data={
            'email': email,
            'password': password,
        }, follow_redirects=False)

    def assert_ok(response, route_name):
        if response.status_code in (200, 302, 303):
            return True, ""
        if response.status_code == 500:
            return False, f"HTTP 500 on {route_name}"
        return False, f"HTTP {response.status_code} on {route_name}"

    print("\n" + "=" * 60)
    print("  CAROAI MVP — TEST DE ESTABILIDAD")
    print("=" * 60)

    # ══════════════════════════════════════════════
    #  1. AUTH
    # ══════════════════════════════════════════════
    print("\n── Auth ──")

    resp = client.get('/auth/login')
    test("GET /auth/login", resp.status_code == 200)

    resp = login('admin@test.com', 'test123')
    test("POST login as admin", resp.status_code in (302, 303))

    resp = login('emp@test.com', 'test123')
    test("POST login as employee", resp.status_code in (302, 303))

    resp = client.post('/auth/login', data={'email': 'admin@test.com', 'password': 'wrong'},
                       follow_redirects=True)
    test("Bad login stays on page", resp.status_code == 200)

    text = resp.data.decode()
    test("Bad login shows error message",
         'inválido' in text.lower() or 'incorrect' in text.lower() or 'intente' in text.lower())

    # ══════════════════════════════════════════════
    #  2. /tasas/
    # ══════════════════════════════════════════════
    print("\n── /tasas/ ──")

    with app.app_context():
        tasa = TasaCambio(moneda_origen='COP', moneda_destino='USD',
                           tasa=4200.0, vigente_desde=datetime.utcnow())
        db.session.add(tasa)
        db.session.commit()
        tasa_id = tasa.id

    # Anon → redirect
    with client.session_transaction() as sess:
        sess.clear()
    resp = client.get('/tasas/')
    test("GET /tasas/ (anon) → redirect", resp.status_code in (302, 303))

    # Admin
    login('admin@test.com', 'test123')
    resp = client.get('/tasas/', follow_redirects=True)
    ok, msg = assert_ok(resp, '/tasas/')
    test("GET /tasas/ (admin) 200", ok, msg)
    test("  → shows COP → USD", 'COP' in resp.data.decode() and 'USD' in resp.data.decode())

    # Create form
    resp = client.get('/tasas/create')
    test("GET /tasas/create", resp.status_code == 200)

    # POST create
    resp = client.post('/tasas/create', data={
        'moneda_origen': 'USD',
        'moneda_destino': 'VES',
        'tasa': 100,
        'vigente_desde': '2026-07-01T00:00',
    }, follow_redirects=True)
    test("POST /tasas/create redirects", resp.status_code == 200)
    test("  → contains updated list", 'USD' in resp.data.decode() and 'VES' in resp.data.decode())

    # Edit form
    resp = client.get(f'/tasas/{tasa_id}/edit')
    test(f"GET /tasas/{tasa_id}/edit", resp.status_code == 200)

    # ══════════════════════════════════════════════
    #  3. SEED: Productos & insumos for sales + inventory tests
    # ══════════════════════════════════════════════
    print("\n── Seed data ──")

    with app.app_context():
        ins = Insumo(nombre='Café test kg', unidad_medida='kg',
                      costo_unitario_cop=72000, stock_actual=10, stock_minimo=2)
        db.session.add(ins)
        db.session.flush()

        prod = Producto(nombre='Café Americano', categoria='bebida',
                         precio_venta_cop=4500, descuenta_inventario=True)
        prod2 = Producto(nombre='Capuchino', categoria='bebida',
                          precio_venta_cop=6500, descuenta_inventario=True)
        db.session.add_all([prod, prod2])
        db.session.commit()

        ins_id = ins.id
        prod_id = prod.id
        prod2_id = prod2.id
        test("Seed: insumo + productos", True)

    # ══════════════════════════════════════════════
    #  4. /sales/ + POS
    # ══════════════════════════════════════════════
    print("\n── /sales/ ──")

    with app.app_context():
        ubi = Ubicacion(nombre='Mesa 1', tipo='mesa')
        db.session.add(ubi)
        db.session.commit()
        ubi_id = ubi.id

        pedido = Pedido(ubicacion_id=ubi_id, total=0, estado='abierto')
        db.session.add(pedido)
        db.session.flush()

        prod_cafe = db.session.get(Producto, prod_id)
        item = PedidoItem(pedido_id=pedido.id, producto_id=prod_cafe.id,
                           cantidad=2, precio_unitario_cop=4500, subtotal_cop=9000)
        db.session.add(item)
        db.session.commit()

        pedido_id = pedido.id
        item_id = item.id

    login('admin@test.com', 'test123')

    resp = client.get('/sales/', follow_redirects=True)
    ok, msg = assert_ok(resp, '/sales/')
    test("GET /sales/ (admin) 200", ok, msg)
    test("  → shows pedido #", f'#{pedido_id}' in resp.data.decode())

    # Employee
    login('emp@test.com', 'test123')
    resp = client.get('/sales/', follow_redirects=True)
    ok, msg = assert_ok(resp, '/sales/')
    test("GET /sales/ (employee) 200", ok, msg)

    # Detail
    login('admin@test.com', 'test123')
    resp = client.get(f'/sales/{pedido_id}', follow_redirects=True)
    ok, msg = assert_ok(resp, f'/sales/{pedido_id}')
    test(f"GET /sales/{pedido_id}/detail", ok, msg)
    test("  → shows products in order", 'Café Americano' in resp.data.decode())

    # Add item
    resp = client.post(f'/sales/{pedido_id}/add_item', data={
        'producto_id': prod2_id,
        'cantidad': 1,
    }, follow_redirects=True)
    test("POST add_item", resp.status_code == 200)
    test("  → now shows Capuchino", 'Capuchino' in resp.data.decode())

    # Remove item
    with app.app_context():
        p = db.session.get(Pedido, pedido_id)
        new_items = [i for i in p.items if i.id not in (item_id,)]
    if new_items:
        new_item_id = new_items[0].id
        resp = client.post(f'/sales/{pedido_id}/remove_item/{new_item_id}',
                           follow_redirects=True)
        test(f"POST remove_item/{new_item_id}", resp.status_code == 200)
        test("  → Capuchino removed", 'Capuchino' not in resp.data.decode())
    else:
        test("POST remove_item (no items to remove)", True, "SKIP")

    # Close form
    resp = client.get(f'/sales/{pedido_id}/close_form')
    ok, msg = assert_ok(resp, f'/sales/{pedido_id}/close_form')
    test("GET close_form", ok, msg)

    # Pay the pedido
    resp = client.post(f'/sales/{pedido_id}/close_form', data={
        'moneda_pago': 'COP',
        'metodo_pago': 'efectivo',
        'observaciones': 'Pago de prueba',
    }, follow_redirects=True)
    test("POST close_form (pay)", resp.status_code == 200)

    with app.app_context():
        p = db.session.get(Pedido, pedido_id)
        test("  → pedido estado = pagado", p.estado == 'pagado',
             f"actual: {p.estado}")

    # ══════════════════════════════════════════════
    #  5. POS
    # ══════════════════════════════════════════════
    print("\n── POS /sales/pos ──")

    login('admin@test.com', 'test123')

    resp = client.get('/sales/pos', follow_redirects=True)
    ok, msg = assert_ok(resp, '/sales/pos')
    test("GET /sales/pos 200", ok, msg)
    test("  → shows Mesa 1", 'Mesa 1' in resp.data.decode())

    resp = client.get(f'/sales/pos/{ubi_id}', follow_redirects=True)
    ok, msg = assert_ok(resp, f'/sales/pos/{ubi_id}')
    test(f"GET /sales/pos/{ubi_id} 200", ok, msg)

    # Open a NEW table via POS
    with app.app_context():
        ubi2 = Ubicacion(nombre='Mesa 2', tipo='mesa')
        db.session.add(ubi2)
        db.session.commit()
        ubi2_id = ubi2.id

    resp = client.post(f'/sales/pos/{ubi2_id}/open', follow_redirects=True)
    test(f"POST /sales/pos/{ubi2_id}/open", resp.status_code == 200)

    with app.app_context():
        p2 = Pedido.query.filter_by(ubicacion_id=ubi2_id, estado='abierto').first()
        if p2:
            p2_id = p2.id
            resp = client.post(f'/sales/{p2_id}/quick_add/{prod_id}',
                               data={'cantidad': 3}, follow_redirects=True)
            test(f"POST quick_add prod#{prod_id}", resp.status_code == 200)
            test("  → Café Americano in POS",
                 'Café Americano' in resp.data.decode())

            # Quick remove
            with app.app_context():
                p2_refreshed = db.session.get(Pedido, p2_id)
                qi_items = [i for i in p2_refreshed.items]
            if qi_items:
                qi_id = qi_items[0].id
                resp = client.post(f'/sales/{p2_id}/quick_remove/{qi_id}',
                                   follow_redirects=True)
                test(f"POST quick_remove item#{qi_id}", resp.status_code == 200)
        else:
            test("POST quick_add pedido check", False, "no abierto pedido found")

    # ══════════════════════════════════════════════
    #  6. /gastos/
    # ══════════════════════════════════════════════
    print("\n── /gastos/ ──")

    with app.app_context():
        gasto = Gasto(concepto='Test gasto', categoria='nomina',
                       monto=100000, moneda='COP', fecha=date.today())
        db.session.add(gasto)
        db.session.commit()
        gasto_id = gasto.id

    login('admin@test.com', 'test123')

    resp = client.get('/gastos/', follow_redirects=True)
    ok, msg = assert_ok(resp, '/gastos/')
    test("GET /gastos/ (admin) 200", ok, msg)
    test("  → shows Test gasto", 'Test gasto' in resp.data.decode())

    # With filters
    resp = client.get(f'/gastos/?mes={date.today().month}&anio={date.today().year}&categoria=nomina',
                      follow_redirects=True)
    ok, msg = assert_ok(resp, '/gastos/ filtered')
    test("GET /gastos/ with filters 200", ok, msg)

    # Create form
    resp = client.get('/gastos/create')
    test("GET /gastos/create", resp.status_code == 200)

    # POST create
    resp = client.post('/gastos/create', data={
        'concepto': 'Nuevo gasto test',
        'categoria': 'insumos',
        'monto': 50000,
        'moneda': 'COP',
        'fecha': '2026-07-19',
    }, follow_redirects=True)
    test("POST /gastos/create 200", resp.status_code == 200)
    test("  → shows new gasto", 'Nuevo gasto test' in resp.data.decode())

    # Edit form
    resp = client.get(f'/gastos/{gasto_id}/edit')
    test(f"GET /gastos/{gasto_id}/edit", resp.status_code == 200)

    # Employee → forbidden
    login('emp@test.com', 'test123')
    resp = client.get('/gastos/', follow_redirects=True)
    test("GET /gastos/ (employee) → redirect",
         '/tables/' in resp.request.url or '/auth/' in resp.request.url)

    # ══════════════════════════════════════════════
    #  7. /inventory/
    # ══════════════════════════════════════════════
    print("\n── /inventory/ ──")

    login('admin@test.com', 'test123')

    resp = client.get('/inventory/', follow_redirects=True)
    ok, msg = assert_ok(resp, '/inventory/')
    test("GET /inventory/ (admin) 200", ok, msg)
    test("  → shows insumo", 'Café test kg' in resp.data.decode())

    # Employee
    login('emp@test.com', 'test123')
    resp = client.get('/inventory/', follow_redirects=True)
    ok, msg = assert_ok(resp, '/inventory/ (employee)')
    test("GET /inventory/ (employee) 200", ok, msg)

    # Movimientos
    login('admin@test.com', 'test123')
    resp = client.get(f'/inventory/{ins_id}/movimientos', follow_redirects=True)
    ok, msg = assert_ok(resp, f'/inventory/{ins_id}/movimientos')
    test(f"GET /inventory/{ins_id}/movimientos 200", ok, msg)

    # Nuevo movimiento form
    resp = client.get(f'/inventory/{ins_id}/movimiento/nuevo')
    test(f"GET /inventory/{ins_id}/movimiento/nuevo", resp.status_code == 200)

    # POST movimiento
    resp = client.post(f'/inventory/{ins_id}/movimiento/nuevo', data={
        'tipo': 'entrada',
        'cantidad': 5,
        'motivo': 'Test compra',
    }, follow_redirects=True)
    test("POST nuevo movimiento (entrada)", resp.status_code == 200)
    test("  → redirect to movimientos page", 'Movimiento' in resp.data.decode() or 'movimiento' in resp.data.decode())

    with app.app_context():
        ins_check = db.session.get(Insumo, ins_id)
        test("  → stock actualizado 10+5=15",
             ins_check.stock_actual == 15,
             f"stock={ins_check.stock_actual}")

    # ══════════════════════════════════════════════
    #  8. /reports/
    # ══════════════════════════════════════════════
    print("\n── /reports/ ──")

    login('admin@test.com', 'test123')

    resp = client.get('/reports/', follow_redirects=True)
    ok, msg = assert_ok(resp, '/reports/')
    test("GET /reports/ (daily, admin) 200", ok, msg)

    resp = client.get('/reports/monthly', follow_redirects=True)
    ok, msg = assert_ok(resp, '/reports/monthly')
    test("GET /reports/monthly (admin) 200", ok, msg)

    # Employee can see daily
    login('emp@test.com', 'test123')
    resp = client.get('/reports/', follow_redirects=True)
    ok, msg = assert_ok(resp, '/reports/ (employee)')
    test("GET /reports/ (employee) 200", ok, msg)

    # Employee cannot see monthly
    login('emp@test.com', 'test123')
    resp = client.get('/reports/monthly', follow_redirects=True)
    test("GET /reports/monthly (employee) → redirect",
         '/tables/' in resp.request.url or '/auth/' in resp.request.url,
         f"→ {resp.request.url}")

    # ══════════════════════════════════════════════
    #  9. /tables/
    # ══════════════════════════════════════════════
    print("\n── /tables/ ──")

    login('admin@test.com', 'test123')

    resp = client.get('/tables/', follow_redirects=True)
    ok, msg = assert_ok(resp, '/tables/')
    test("GET /tables/ 200", ok, msg)
    test("  → shows Mesa 1 and Mesa 2",
         'Mesa 1' in resp.data.decode() and 'Mesa 2' in resp.data.decode())

    # Open a free ubicacion
    with app.app_context():
        ubi3 = Ubicacion(nombre='Mesa 3', tipo='mesa')
        db.session.add(ubi3)
        db.session.commit()
        ubi3_id = ubi3.id

    resp = client.post(f'/tables/open/{ubi3_id}', follow_redirects=True)
    test(f"POST /tables/open/{ubi3_id} 200", resp.status_code == 200)
    test("  → redirects to sales detail", 'Pedido' in resp.data.decode() or 'pedido' in resp.data.decode())

    # Open again → should redirect (already occupied)
    resp = client.post(f'/tables/open/{ubi3_id}', follow_redirects=True)
    test(f"POST /tables/open/{ubi3_id} again 200 (no crash)", resp.status_code == 200)

    # ══════════════════════════════════════════════
    #  10. Void / Restore (anulación lógica)
    # ══════════════════════════════════════════════
    print("\n── Void / Restore ──")

    login('admin@test.com', 'test123')

    with app.app_context():
        # Find a pagado pedido or create one
        p_to_pay = Pedido.query.filter_by(estado='abierto').first()
        if p_to_pay:
            p_to_pay.estado = 'pagado'
            p_to_pay.pagado_en = datetime.utcnow()
            p_to_pay.moneda_pago = 'COP'
            p_to_pay.metodo_pago = 'efectivo'
            db.session.commit()
            pay_id = p_to_pay.id

            if p_to_pay.items:
                vi = p_to_pay.items[0]

                # Void item
                resp = client.post(f'/sales/{pay_id}/void_item/{vi.id}',
                                   data={'motivo': 'Test anulación'},
                                   follow_redirects=True)
                test(f"POST void_item #{vi.id}", resp.status_code == 200)
                test("  → flash shows anulado", 'anulado' in resp.data.decode().lower())

                with app.app_context():
                    vi_check = db.session.get(PedidoItem, vi.id)
                    test("  → item.anulado = True",
                         vi_check.anulado == True,
                         f"anulado={vi_check.anulado}")

                # Restore item
                resp = client.post(f'/sales/{pay_id}/restore_item/{vi.id}',
                                   follow_redirects=True)
                test(f"POST restore_item #{vi.id}", resp.status_code == 200)
                test("  → flash shows restaurado",
                     'restaurado' in resp.data.decode().lower())

                with app.app_context():
                    vi_check = db.session.get(PedidoItem, vi.id)
                    test("  → item.anulado = False",
                         vi_check.anulado == False,
                         f"anulado={vi_check.anulado}")

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
    # Cleanup
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    sys.exit(0 if success else 1)
