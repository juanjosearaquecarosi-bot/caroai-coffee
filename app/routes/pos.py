from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort
from flask_login import login_required
from ..models import db, Mesa, Pedido, PedidoItem, Producto, TasaCambio
from ..utils.decorators import role_required
from datetime import datetime, date


def _get_tasas():
    """Retorna (tasa_usd, tasa_bs): cuántos COP vale 1 USD y 1 BS."""
    tasa_usd = 4200.0
    tasa_bs = 6.0

    t = TasaCambio.query.filter_by(
        moneda_origen='USD', moneda_destino='COP'
    ).order_by(TasaCambio.vigente_desde.desc()).first()
    if t:
        tasa_usd = t.tasa
    else:
        t = TasaCambio.query.filter_by(
            moneda_origen='COP', moneda_destino='USD'
        ).order_by(TasaCambio.vigente_desde.desc()).first()
        if t and t.tasa > 0:
            tasa_usd = round(1 / t.tasa, 2)

    t = TasaCambio.query.filter_by(
        moneda_origen='VES', moneda_destino='COP'
    ).order_by(TasaCambio.vigente_desde.desc()).first()
    if t:
        tasa_bs = t.tasa
    else:
        t = TasaCambio.query.filter_by(
            moneda_origen='COP', moneda_destino='VES'
        ).order_by(TasaCambio.vigente_desde.desc()).first()
        if t and t.tasa > 0:
            tasa_bs = round(1 / t.tasa, 2)

    return tasa_usd, tasa_bs

pos_bp = Blueprint('pos', __name__, url_prefix='/pos')

# ══════════════════════════════════════════════
#  1. MAPA DE MESAS
# ══════════════════════════════════════════════

@pos_bp.route('/')
@login_required
@role_required('admin', 'employee')
def index():
    """Mapa de mesas con estado y pedido activo."""
    mesas = Mesa.query.order_by(Mesa.id).all()

    # Para cada mesa, detectar si tiene pedido abierto con items
    for m in mesas:
        m._pedido_activo = Pedido.query.filter_by(
            mesa_id=m.id, estado='abierto'
        ).first()
        m._tiene_items = m._pedido_activo and len(m._pedido_activo.items) > 0 if m._pedido_activo else False
        m._items_count = len(m._pedido_activo.items) if m._pedido_activo else 0

    stats = {
        'libres': sum(1 for m in mesas if m.estado == 'libre'),
        'ocupadas': sum(1 for m in mesas if m.estado == 'ocupada'),
        'con_items': sum(1 for m in mesas if getattr(m, '_tiene_items', False)),
    }

    return render_template('pos/map.html', mesas=mesas, stats=stats)


# ══════════════════════════════════════════════
#  2. ABRIR MESA
# ══════════════════════════════════════════════

@pos_bp.route('/<int:mesa_id>/open', methods=['POST'])
@login_required
@role_required('admin', 'employee')
def open_mesa(mesa_id):
    mesa = db.session.get(Mesa, mesa_id)
    if not mesa:
        flash('Mesa no encontrada.', 'danger')
        return redirect(url_for('pos.index'))

    if mesa.estado != 'libre':
        flash(f'{mesa.nombre} no está disponible.', 'warning')
        return redirect(url_for('pos.index'))

    # Crear pedido y marcar mesa
    mesa.estado = 'ocupada'
    mesa.fecha_apertura = datetime.utcnow()
    pedido = Pedido(mesa_id=mesa.id, total=0, estado='abierto')
    db.session.add(pedido)
    db.session.commit()

    flash(f'{mesa.nombre} abierta. Pedido #{pedido.id} creado.', 'success')
    return redirect(url_for('pos.mesa', mesa_id=mesa.id))


# ══════════════════════════════════════════════
#  3. POS POR MESA
# ══════════════════════════════════════════════

@pos_bp.route('/<int:mesa_id>')
@login_required
@role_required('admin', 'employee')
def mesa(mesa_id):
    mesa = db.session.get(Mesa, mesa_id)
    if not mesa:
        flash('Mesa no encontrada.', 'danger')
        return redirect(url_for('pos.index'))

    # Buscar pedido abierto o mostrar estado libre
    pedido = Pedido.query.filter_by(mesa_id=mesa.id, estado='abierto').first()
    productos = Producto.query.order_by(Producto.tipo, Producto.nombre).all()
    catalogo = {
        "bebida": [p for p in productos if (p.tipo or "").strip().lower() == "bebida"],
        "comida": [p for p in productos if (p.tipo or "").strip().lower() == "comida"],
        "grano": [p for p in productos if (p.tipo or "").strip().lower() == "grano"],
        "cerveza": [p for p in productos if (p.tipo or "").strip().lower() == "cerveza"],
    }

    total_cop = 0
    if pedido:
        total_cop = sum(i.subtotal_cop for i in pedido.items)

    tasa_usd, tasa_bs = _get_tasas()

    return render_template('pos/mesa.html',
                           mesa=mesa, pedido=pedido,
                           catalogo=catalogo, productos=productos,
                           total_cop=total_cop,
                           tasa_usd=tasa_usd, tasa_bs=tasa_bs)


# ══════════════════════════════════════════════
#  4. AGREGAR PRODUCTO
# ══════════════════════════════════════════════

@pos_bp.route('/<int:mesa_id>/add', methods=['POST'])
@login_required
@role_required('admin', 'employee')
def add_item(mesa_id):
    mesa = db.session.get(Mesa, mesa_id)
    if not mesa:
        return jsonify({'ok': False, 'error': 'Mesa no encontrada'}), 404

    producto_id = request.form.get('producto_id', type=int)
    if not producto_id:
        return jsonify({'ok': False, 'error': 'producto_id requerido'}), 400

    # Buscar o crear pedido abierto
    pedido = Pedido.query.filter_by(mesa_id=mesa.id, estado='abierto').first()
    if not pedido:
        if mesa.estado == 'libre':
            mesa.estado = 'ocupada'
            mesa.fecha_apertura = datetime.utcnow()
        pedido = Pedido(mesa_id=mesa.id, total=0, estado='abierto')
        db.session.add(pedido)
        db.session.flush()

    producto = db.session.get(Producto, producto_id)
    if not producto:
        return jsonify({'ok': False, 'error': 'Producto no encontrado'}), 404

    cantidad = request.form.get('cantidad', 1, type=int)
    if cantidad <= 0:
        cantidad = 1

    precio = producto.precio_cop or producto.precio_venta_cop or 0

    item_existente = next((i for i in pedido.items if i.producto_id == producto_id), None)
    if item_existente:
        item_existente.cantidad += cantidad
        item_existente.subtotal_cop = item_existente.precio_unitario_cop * item_existente.cantidad
    else:
        item = PedidoItem(
            pedido_id=pedido.id,
            producto_id=producto.id,
            cantidad=cantidad,
            precio_unitario_cop=precio,
            subtotal_cop=precio * cantidad,
        )
        db.session.add(item)

    db.session.commit()

    total = sum(i.subtotal_cop for i in pedido.items)

    if _is_ajax():
        return jsonify({
            'ok': True,
            'items': _items_json(pedido),
            'total': total,
        })

    flash(f'{producto.nombre} x{cantidad} agregado.', 'success')
    return redirect(url_for('pos.mesa', mesa_id=mesa.id))


# ══════════════════════════════════════════════
#  5. QUITAR PRODUCTO
# ══════════════════════════════════════════════

@pos_bp.route('/<int:mesa_id>/remove/<int:item_id>', methods=['POST'])
@login_required
@role_required('admin', 'employee')
def remove_item(mesa_id, item_id):
    pedido = Pedido.query.filter_by(mesa_id=mesa_id, estado='abierto').first()
    if not pedido:
        return jsonify({'ok': False, 'error': 'No hay pedido abierto'}), 404

    item = db.session.get(PedidoItem, item_id)
    if not item or item.pedido_id != pedido.id:
        return jsonify({'ok': False, 'error': 'Item no encontrado'}), 404

    if item.cantidad > 1:
        item.cantidad -= 1
        item.subtotal_cop = item.precio_unitario_cop * item.cantidad
    else:
        db.session.delete(item)

    db.session.commit()

    total = sum(i.subtotal_cop for i in pedido.items)

    if _is_ajax():
        return jsonify({
            'ok': True,
            'items': _items_json(pedido),
            'total': total,
        })

    flash('Producto quitado.', 'success')
    return redirect(url_for('pos.mesa', mesa_id=mesa_id))


# ══════════════════════════════════════════════
#  6. COBRAR / CERRAR MESA
# ══════════════════════════════════════════════

@pos_bp.route('/<int:mesa_id>/charge', methods=['POST'])
@login_required
@role_required('admin', 'employee')
def charge(mesa_id):
    mesa = db.session.get(Mesa, mesa_id)
    pedido = Pedido.query.filter_by(mesa_id=mesa_id, estado='abierto').first()

    if not pedido or not pedido.items:
        flash('No hay productos para cobrar.', 'warning')
        return redirect(url_for('pos.mesa', mesa_id=mesa_id))

    moneda_pago = request.form.get('moneda_pago', 'COP')
    metodo_pago = request.form.get('metodo_pago', 'efectivo')
    tasa_str = request.form.get('tasa_aplicada', '').strip()
    total_moneda_str = request.form.get('total_pagado_moneda', '').strip()
    observaciones = request.form.get('observaciones', '').strip() or None

    now = datetime.utcnow()
    total_cop = sum(i.subtotal_cop for i in pedido.items)
    pedido.total = total_cop
    pedido.estado = 'pagado'
    pedido.moneda_pago = moneda_pago
    pedido.metodo_pago = metodo_pago
    pedido.tasa_aplicada = float(tasa_str) if tasa_str else (1.0 if moneda_pago == 'COP' else None)
    pedido.total_pagado_moneda = float(total_moneda_str) if total_moneda_str else None
    pedido.observaciones = observaciones
    pedido.pagado_en = now

    # Liberar mesa
    mesa.estado = 'libre'
    mesa.fecha_apertura = None

    db.session.commit()

    flash_moneda = f'{moneda_pago} {total_moneda_str}' if total_moneda_str else f'${total_cop:,} COP'
    flash(f'✅ {mesa.nombre} cobrada · {flash_moneda}', 'success')
    return redirect(url_for('pos.index'))


# ══════════════════════════════════════════════
#  7. MARCAR COMO PENDIENTE
# ══════════════════════════════════════════════

@pos_bp.route('/<int:mesa_id>/pendiente', methods=['POST'])
@login_required
@role_required('admin', 'employee')
def pendiente(mesa_id):
    pedido = Pedido.query.filter_by(mesa_id=mesa_id, estado='abierto').first()
    if not pedido:
        flash('No hay pedido abierto.', 'warning')
        return redirect(url_for('pos.index'))

    pedido.estado = 'pendiente'
    db.session.commit()

    flash(f'Pedido #{pedido.id} marcado como pendiente.', 'info')
    return redirect(url_for('pos.index'))


# ══════════════════════════════════════════════
#  8. HISTORIAL
# ══════════════════════════════════════════════

@pos_bp.route('/history')
@login_required
@role_required('admin', 'employee')
def history():
    pedidos = Pedido.query.filter(
        Pedido.estado.in_(['pagado', 'pendiente'])
    ).order_by(Pedido.fecha_hora.desc()).all()
    return render_template('pos/history.html', pedidos=pedidos)


# ══════════════════════════════════════════════
#  9. DETALLE DE PEDIDO
# ══════════════════════════════════════════════

@pos_bp.route('/pedido/<int:pedido_id>')
@login_required
@role_required('admin', 'employee')
def detail(pedido_id):
    pedido = db.session.get(Pedido, pedido_id)
    if not pedido or pedido.estado not in ('pagado', 'pendiente'):
        abort(404)
    return render_template('pos/detail.html', pedido=pedido)


# ══════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════

def _is_ajax():
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def _items_json(pedido):
    return [{
        'id': i.id,
        'producto_id': i.producto_id,
        'nombre': i.producto.nombre,
        'cantidad': i.cantidad,
        'precio': i.precio_unitario_cop,
        'subtotal': i.subtotal_cop,
    } for i in pedido.items]
