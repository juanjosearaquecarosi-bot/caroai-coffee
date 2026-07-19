from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session, abort
from flask_login import login_required
from ..models import db, Producto, Pedido, PedidoItem, Mesa
from ..utils.decorators import role_required
from datetime import datetime

sales_bp = Blueprint('sales', __name__)

# ──────────────────────────────────────────────
#  HELPERS: session cart management
# ──────────────────────────────────────────────

def _cart():
    """Get the current session cart list."""
    return session.get('cart', [])


def _set_cart(cart):
    session['cart'] = cart
    session.modified = True


def _clear_cart():
    session.pop('cart', None)
    session.modified = True


def _cart_total(cart):
    return sum(item['subtotal'] for item in cart)


def _get_caja_id():
    """Return the id of the default 'Caja' location, creating it if missing."""
    caja = Mesa.query.filter_by(nombre='Caja').first()
    if not caja:
        caja = Mesa(nombre='Caja')
        db.session.add(caja)
        db.session.commit()
    return caja.id


# ══════════════════════════════════════════════
#  MAIN — CASH REGISTER
# ══════════════════════════════════════════════

@sales_bp.route('/')
@login_required
@role_required('admin', 'employee')
def index():
    """POS cash-register main page."""
    productos = Producto.query.order_by(Producto.categoria, Producto.nombre).all()
    cart = _cart()
    total = _cart_total(cart)
    return render_template('sales/pos.html', productos=productos, cart=cart, total=total)


# ──────────────────────────────────────────────
#  ADD ITEM
# ──────────────────────────────────────────────

@sales_bp.route('/add', methods=['POST'])
@login_required
@role_required('admin', 'employee')
def add_item():
    producto_id = request.form.get('producto_id', type=int)
    cantidad = request.form.get('cantidad', type=int, default=1)

    if not producto_id or cantidad <= 0:
        if _is_ajax():
            return jsonify({'ok': False, 'error': 'Datos inválidos'}), 400
        flash('Datos inválidos.', 'warning')
        return redirect(url_for('sales.index'))

    producto = db.session.get(Producto, producto_id)
    if not producto:
        if _is_ajax():
            return jsonify({'ok': False, 'error': 'Producto no encontrado'}), 404
        flash('Producto no encontrado.', 'warning')
        return redirect(url_for('sales.index'))

    cart = _cart()

    # Accumulate if already in cart
    for item in cart:
        if item['producto_id'] == producto_id:
            item['cantidad'] += cantidad
            item['subtotal'] = item['precio'] * item['cantidad']
            break
    else:
        cart.append({
            'producto_id': producto.id,
            'nombre': producto.nombre,
            'cantidad': cantidad,
            'precio': producto.precio_venta_cop,
            'subtotal': producto.precio_venta_cop * cantidad,
        })

    _set_cart(cart)
    total = _cart_total(cart)

    if _is_ajax():
        return jsonify({'ok': True, 'cart': cart, 'total': total})

    flash(f'{producto.nombre} x{cantidad} agregado.', 'success')
    return redirect(url_for('sales.index'))


# ──────────────────────────────────────────────
#  REMOVE / DECREMENT ITEM
# ──────────────────────────────────────────────

@sales_bp.route('/remove/<int:item_index>', methods=['POST'])
@login_required
@role_required('admin', 'employee')
def remove_item(item_index):
    cart = _cart()

    if item_index < 0 or item_index >= len(cart):
        if _is_ajax():
            return jsonify({'ok': False, 'error': 'Item no encontrado'}), 404
        flash('Item no encontrado.', 'warning')
        return redirect(url_for('sales.index'))

    if cart[item_index]['cantidad'] > 1:
        cart[item_index]['cantidad'] -= 1
        cart[item_index]['subtotal'] = cart[item_index]['precio'] * cart[item_index]['cantidad']
    else:
        cart.pop(item_index)

    _set_cart(cart)
    total = _cart_total(cart)

    if _is_ajax():
        return jsonify({'ok': True, 'cart': cart, 'total': total})

    flash('Producto quitado.', 'success')
    return redirect(url_for('sales.index'))


# ──────────────────────────────────────────────
#  CHARGE / CHECKOUT
# ──────────────────────────────────────────────

@sales_bp.route('/charge', methods=['POST'])
@login_required
@role_required('admin', 'employee')
def charge():
    cart = _cart()
    if not cart:
        flash('No hay productos en la venta.', 'warning')
        return redirect(url_for('sales.index'))

    moneda_pago = request.form.get('moneda_pago', 'COP')
    metodo_pago = request.form.get('metodo_pago', 'efectivo')
    observaciones = request.form.get('observaciones', '').strip() or None

    total = _cart_total(cart)
    caja_id = _get_caja_id()
    now = datetime.utcnow()

    pedido = Pedido(
        ubicacion_id=caja_id,
        total=total,
        estado='pagado',
        moneda_pago=moneda_pago,
        metodo_pago=metodo_pago,
        observaciones=observaciones,
        pagado_en=now,
        fecha_hora=now,
    )
    db.session.add(pedido)
    db.session.flush()

    for item in cart:
        db.session.add(PedidoItem(
            pedido_id=pedido.id,
            producto_id=item['producto_id'],
            cantidad=item['cantidad'],
            precio_unitario_cop=item['precio'],
            subtotal_cop=item['subtotal'],
        ))

    db.session.commit()
    _clear_cart()

    flash(f'✅ Venta #{pedido.id} registrada · ${total:,} COP', 'success')
    return redirect(url_for('sales.index'))


# ──────────────────────────────────────────────
#  HISTORY
# ──────────────────────────────────────────────

@sales_bp.route('/history')
@login_required
@role_required('admin', 'employee')
def history():
    pedidos = Pedido.query.filter_by(estado='pagado').order_by(Pedido.fecha_hora.desc()).all()
    return render_template('sales/history.html', pedidos=pedidos)


# ──────────────────────────────────────────────
#  DETAIL (view a single paid order)
# ──────────────────────────────────────────────

@sales_bp.route('/<int:pedido_id>')
@login_required
@role_required('admin', 'employee')
def detail(pedido_id):
    pedido = db.session.get(Pedido, pedido_id)
    if not pedido or pedido.estado != 'pagado':
        abort(404)
    items = pedido.items
    total = pedido.total
    return render_template('sales/detail.html', pedido=pedido, items=items, total=total)


# ──────────────────────────────────────────────
#  INTERNAL HELPERS
# ──────────────────────────────────────────────

def _is_ajax():
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'
