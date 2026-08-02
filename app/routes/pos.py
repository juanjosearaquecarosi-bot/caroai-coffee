import logging
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort
from flask_login import login_required, current_user
from ..models import db, Mesa, Pedido, PedidoItem, Producto
from ..utils.decorators import role_required
from ..utils.currency import obtener_tasas_cop, convertir_cop_a
from datetime import datetime, date

logger = logging.getLogger(__name__)

pos_bp = Blueprint('pos', __name__, url_prefix='/pos')

# ══════════════════════════════════════════════
#  1. MAPA DE MESAS
# ══════════════════════════════════════════════

@pos_bp.route('/')
@login_required
@role_required('admin', 'empleado')
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
@role_required('admin', 'empleado')
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
@role_required('admin', 'empleado')
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

    # ── DEBUG: log cantidades de productos ──
    logger.info(
        "📦 POS mesa=%s — total productos: %d  |  bebida=%d  comida=%d  grano=%d  cerveza=%d",
        mesa.nombre, len(productos),
        len(catalogo["bebida"]), len(catalogo["comida"]),
        len(catalogo["grano"]), len(catalogo["cerveza"]),
    )

    total_cop = 0
    if pedido:
        total_cop = sum(i.subtotal_cop for i in pedido.items)

    tasa_usd, tasa_bs, *_ = obtener_tasas_cop()

    return render_template('pos/mesa.html',
                           mesa=mesa, pedido=pedido,
                           catalogo=catalogo,
                           total_cop=total_cop,
                           tasa_usd=tasa_usd, tasa_bs=tasa_bs)


# ══════════════════════════════════════════════
#  4. AGREGAR PRODUCTO
# ══════════════════════════════════════════════

@pos_bp.route('/<int:mesa_id>/add', methods=['POST'])
@login_required
@role_required('admin', 'empleado')
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
@role_required('admin', 'empleado')
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
@role_required('admin', 'empleado')
def charge(mesa_id):
    mesa = db.session.get(Mesa, mesa_id)
    pedido = Pedido.query.filter_by(mesa_id=mesa_id, estado='abierto').first()

    if not pedido or not pedido.items:
        if _is_ajax():
            return jsonify({'ok': False, 'error': 'No hay productos para cobrar.'}), 400
        flash('No hay productos para cobrar.', 'warning')
        return redirect(url_for('pos.mesa', mesa_id=mesa_id))

    moneda_pago = request.form.get('moneda_pago', 'COP')
    metodo_pago = request.form.get('metodo_pago', 'efectivo')
    tasa_str = request.form.get('tasa_aplicada', '').strip()
    total_moneda_str = request.form.get('total_pagado_moneda', '').strip()
    observaciones = request.form.get('observaciones', '').strip() or None

    now = datetime.utcnow()
    total_cop = sum(i.subtotal_cop for i in pedido.items)

    # ── Validar tasa activa si la moneda no es COP ──
    if moneda_pago != 'COP':
        monto_convertido, tasa_val, error_msg = convertir_cop_a(total_cop, moneda_pago)
        if error_msg:
            if _is_ajax():
                return jsonify({'ok': False, 'error': error_msg}), 400
            flash(error_msg, 'warning')
            return redirect(url_for('pos.mesa', mesa_id=mesa_id))
        # Solo admin puede sobreescribir la tasa manualmente; empleado usa la de BD
        if current_user.rol == 'admin' and tasa_str:
            tasa_final = float(tasa_str)
            total_moneda_final = float(total_moneda_str) if total_moneda_str else monto_convertido
        else:
            tasa_final = tasa_val
            total_moneda_final = monto_convertido
    else:
        tasa_final = 1.0
        total_moneda_final = None

    # ── Pedido ──
    pedido.total = total_cop
    pedido.estado = 'pagado'
    pedido.moneda_pago = moneda_pago
    pedido.metodo_pago = metodo_pago
    pedido.tasa_aplicada = tasa_final
    pedido.total_pagado_moneda = total_moneda_final
    pedido.observaciones = observaciones
    pedido.pagado_en = now

    # Liberar mesa
    mesa.estado = 'libre'
    mesa.fecha_apertura = None

    db.session.commit()

    flash_moneda = f'{moneda_pago} {total_moneda_final}' if total_moneda_final else f'${total_cop:,} COP'

    if _is_ajax():
        return jsonify({
            'ok': True,
            'message': f'✅ {mesa.nombre} cobrada · {flash_moneda}',
            'pedido_id': pedido.id,
            'mesa_nombre': mesa.nombre,
        })

    flash(f'✅ {mesa.nombre} cobrada · {flash_moneda}', 'success')
    return redirect(url_for('pos.index'))


# ══════════════════════════════════════════════
#  7. MARCAR COMO PENDIENTE (libera mesa)
# ══════════════════════════════════════════════

@pos_bp.route('/<int:mesa_id>/pendiente', methods=['POST'])
@login_required
@role_required('admin', 'empleado')
def pendiente(mesa_id):
    mesa = db.session.get(Mesa, mesa_id)
    pedido = Pedido.query.filter_by(mesa_id=mesa_id, estado='abierto').first()
    if not pedido:
        flash('No hay pedido abierto.', 'warning')
        return redirect(url_for('pos.index'))

    pedido.estado = 'pendiente'
    # Liberar la mesa forzadamente
    mesa.estado = 'libre'
    mesa.fecha_apertura = None
    db.session.commit()

    flash(f'Pedido #{pedido.id} marcado como pendiente. Mesa {mesa.nombre} liberada.', 'info')
    return redirect(url_for('pos.index'))


# ══════════════════════════════════════════════
#  8. HISTORIAL
# ══════════════════════════════════════════════

@pos_bp.route('/history')
@login_required
@role_required('admin', 'empleado')
def history():
    pedidos = Pedido.query.filter(
        Pedido.estado.in_(['pagado', 'pendiente', 'abierto', 'anulado'])
    ).order_by(Pedido.fecha_hora.desc()).all()
    return render_template('pos/history.html', pedidos=pedidos)


# ══════════════════════════════════════════════
#  9. DETALLE DE PEDIDO
# ══════════════════════════════════════════════

@pos_bp.route('/pedido/<int:pedido_id>')
@login_required
@role_required('admin', 'empleado')
def detail(pedido_id):
    pedido = db.session.get(Pedido, pedido_id)
    if not pedido or pedido.estado not in ('pagado', 'pendiente'):
        abort(404)
    return render_template('pos/detail.html', pedido=pedido)


# ══════════════════════════════════════════════
#  9B. EDITAR PEDIDO (solo abierto)
# ══════════════════════════════════════════════

@pos_bp.route('/pedido/<int:pedido_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'empleado')
def edit(pedido_id):
    """Editar un pedido abierto: cambiar cantidades, eliminar líneas, agregar productos."""
    pedido = db.session.get(Pedido, pedido_id)
    if not pedido:
        flash('Pedido no encontrado.', 'danger')
        return redirect(url_for('pos.history'))

    if pedido.estado != 'abierto':
        if current_user.rol == 'admin':
            flash('Este pedido ya está cerrado. Solo puedes anularlo desde el detalle.', 'warning')
            return redirect(url_for('pos.detail', pedido_id=pedido.id))
        flash('Este pedido no está abierto y no puede editarse.', 'warning')
        return redirect(url_for('pos.history'))

    mesa = db.session.get(Mesa, pedido.mesa_id)
    productos = Producto.query.order_by(Producto.tipo, Producto.nombre).all()
    catalogo = {
        "bebida": [p for p in productos if (p.tipo or "").strip().lower() == "bebida"],
        "comida": [p for p in productos if (p.tipo or "").strip().lower() == "comida"],
        "grano": [p for p in productos if (p.tipo or "").strip().lower() == "grano"],
        "cerveza": [p for p in productos if (p.tipo or "").strip().lower() == "cerveza"],
    }

    if request.method == 'POST':
        action = request.form.get('action', '')

        if action == 'update_qty':
            item_id = request.form.get('item_id', type=int)
            cantidad = request.form.get('cantidad', type=int, default=1)
            item = db.session.get(PedidoItem, item_id)
            if item and item.pedido_id == pedido.id:
                if cantidad <= 0:
                    db.session.delete(item)
                else:
                    item.cantidad = cantidad
                    item.subtotal_cop = item.precio_unitario_cop * cantidad
                db.session.commit()

        elif action == 'remove_item':
            item_id = request.form.get('item_id', type=int)
            item = db.session.get(PedidoItem, item_id)
            if item and item.pedido_id == pedido.id:
                db.session.delete(item)
                db.session.commit()

        elif action == 'add_product':
            producto_id = request.form.get('producto_id', type=int)
            cantidad = request.form.get('cantidad', 1, type=int)
            producto = db.session.get(Producto, producto_id) if producto_id else None
            if producto and cantidad > 0:
                precio = producto.precio_cop or producto.precio_venta_cop or 0
                item_existente = next((i for i in pedido.items if i.producto_id == producto_id), None)
                if item_existente:
                    item_existente.cantidad += cantidad
                    item_existente.subtotal_cop = item_existente.precio_unitario_cop * item_existente.cantidad
                else:
                    db.session.add(PedidoItem(
                        pedido_id=pedido.id,
                        producto_id=producto.id,
                        cantidad=cantidad,
                        precio_unitario_cop=precio,
                        subtotal_cop=precio * cantidad,
                    ))
                db.session.commit()

        elif action == 'add_manual':
            descripcion = request.form.get('descripcion', '').strip()
            monto = request.form.get('monto', type=int, default=0)
            cantidad = request.form.get('cantidad', 1, type=int)
            if descripcion and monto > 0:
                db.session.add(PedidoItem(
                    pedido_id=pedido.id,
                    producto_id=None,
                    cantidad=cantidad,
                    precio_unitario_cop=monto,
                    subtotal_cop=monto * cantidad,
                    nota=descripcion,
                ))
                db.session.commit()

        # Recalcular total
        pedido.total = sum(i.subtotal_cop for i in pedido.items)
        db.session.commit()

        flash('Pedido actualizado.', 'success')
        return redirect(url_for('pos.edit', pedido_id=pedido.id))

    total_cop = sum(i.subtotal_cop for i in pedido.items)
    tasa_usd, tasa_bs, *_ = obtener_tasas_cop()
    return render_template('pos/edit.html',
                           pedido=pedido, mesa=mesa,
                           catalogo=catalogo,
                           total_cop=total_cop,
                           tasa_usd=tasa_usd, tasa_bs=tasa_bs)


# ══════════════════════════════════════════════
#  9C. ELIMINAR PEDIDO (hard delete, solo abierto)
# ══════════════════════════════════════════════

@pos_bp.route('/pedido/<int:pedido_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete(pedido_id):
    """Elimina físicamente un pedido abierto. Solo admin."""
    pedido = db.session.get(Pedido, pedido_id)
    if not pedido:
        flash('Pedido no encontrado.', 'danger')
        return redirect(url_for('pos.history'))

    if pedido.estado != 'abierto':
        flash('Solo se pueden eliminar pedidos abiertos. Usa anular para pedidos cerrados.', 'warning')
        return redirect(url_for('pos.history'))

    mesa = db.session.get(Mesa, pedido.mesa_id)
    if mesa:
        mesa.estado = 'libre'
        mesa.fecha_apertura = None

    db.session.delete(pedido)
    db.session.commit()

    flash(f'🗑️ Pedido #{pedido_id} eliminado permanentemente.', 'info')
    return redirect(url_for('pos.history'))


# ══════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════

def _is_ajax():
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


# ══════════════════════════════════════════════
#  10. AÑADIR MONTO MANUAL
# ══════════════════════════════════════════════

@pos_bp.route('/<int:mesa_id>/add_manual', methods=['POST'])
@login_required
@role_required('admin', 'empleado')
def add_manual(mesa_id):
    """Agrega un cargo manual (monto sin producto) al pedido abierto."""
    mesa = db.session.get(Mesa, mesa_id)
    if not mesa:
        return jsonify({'ok': False, 'error': 'Mesa no encontrada'}), 404

    pedido = Pedido.query.filter_by(mesa_id=mesa.id, estado='abierto').first()
    if not pedido:
        if mesa.estado == 'libre':
            mesa.estado = 'ocupada'
            mesa.fecha_apertura = datetime.utcnow()
        pedido = Pedido(mesa_id=mesa.id, total=0, estado='abierto')
        db.session.add(pedido)
        db.session.flush()

    descripcion = request.form.get('descripcion', '').strip()
    monto = request.form.get('monto', type=int, default=0)
    cantidad = request.form.get('cantidad', 1, type=int)
    if cantidad < 1:
        cantidad = 1

    if not descripcion:
        return jsonify({'ok': False, 'error': 'Descripción requerida'}), 400
    if monto <= 0:
        return jsonify({'ok': False, 'error': 'El monto debe ser mayor a 0'}), 400

    item = PedidoItem(
        pedido_id=pedido.id,
        producto_id=None,
        cantidad=cantidad,
        precio_unitario_cop=monto,
        subtotal_cop=monto * cantidad,
        nota=descripcion,
    )
    db.session.add(item)
    db.session.commit()

    total = sum(i.subtotal_cop for i in pedido.items)

    if _is_ajax():
        return jsonify({
            'ok': True,
            'items': _items_json(pedido),
            'total': total,
            'message': f'💰 Cargo manual «{descripcion}» agregado · ${monto:,}',
        })

    flash(f'💰 Cargo manual «{descripcion}» · ${monto:,}', 'success')
    return redirect(url_for('pos.mesa', mesa_id=mesa.id))


# ══════════════════════════════════════════════
#  11. ANULAR PEDIDO (solo admin)
# ══════════════════════════════════════════════

@pos_bp.route('/pedido/<int:pedido_id>/anular', methods=['POST'])
@login_required
@role_required('admin')
def anular(pedido_id):
    """Anula un pedido pagado o pendiente. Solo admin."""
    pedido = db.session.get(Pedido, pedido_id)
    if not pedido:
        flash('Pedido no encontrado.', 'danger')
        return redirect(url_for('pos.history'))

    if pedido.estado not in ('pagado', 'pendiente'):
        flash(f'No se puede anular un pedido en estado «{pedido.estado}».', 'warning')
        return redirect(url_for('pos.history'))

    motivo = request.form.get('motivo', '').strip()

    pedido.estado = 'anulado'

    # Anular lógicamente todos los items
    now = datetime.utcnow()
    for item in pedido.items:
        item.anulado_en = now
        item.motivo_anulacion = motivo if motivo else 'Anulado por administrador'

    db.session.commit()
    flash(f'🗑️ Pedido #{pedido.id} anulado.' + (f' Motivo: {motivo}' if motivo else ''), 'warning')
    return redirect(url_for('pos.history'))


def _items_json(pedido):
    return [{
        'id': i.id,
        'producto_id': i.producto_id,
        'nombre': i.nota or (i.producto.nombre if i.producto else 'Cargo manual'),
        'cantidad': i.cantidad,
        'precio': i.precio_unitario_cop,
        'subtotal': i.subtotal_cop,
        'manual': i.producto_id is None,
    } for i in pedido.items]
