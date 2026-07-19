from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required
from ..models import db, Ubicacion, Pedido, Producto, PedidoItem, MovimientoInventario, Receta
from ..utils.decorators import role_required
from datetime import datetime

sales_bp = Blueprint('sales', __name__)


@sales_bp.route('/')
@login_required
@role_required('admin', 'employee')
def index():
    pedidos = Pedido.query.order_by(Pedido.fecha_hora.desc()).all()
    return render_template('sales/index.html', pedidos=pedidos)


@sales_bp.route('/<int:pedido_id>')
@login_required
@role_required('admin', 'employee')
def detail(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)
    productos = Producto.query.order_by(Producto.nombre).all()
    total_cop = sum(item.subtotal_cop for item in pedido.items)
    return render_template('sales/detail.html', pedido=pedido, productos=productos, total_cop=total_cop)


# ──────────────────────────────────────────────
#  AGREGAR ITEM AL PEDIDO
# ──────────────────────────────────────────────
@sales_bp.route('/<int:pedido_id>/add_item', methods=['POST'])
@login_required
@role_required('admin', 'employee')
def add_item(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)
    if pedido.estado != 'abierto':
        flash('Solo se pueden agregar items a un pedido abierto.', 'warning')
        return redirect(url_for('sales.detail', pedido_id=pedido.id))

    producto_id = request.form.get('producto_id')
    cantidad = request.form.get('cantidad', type=int, default=1)
    if not producto_id or cantidad <= 0:
        flash('Datos inválidos.', 'warning')
        return redirect(url_for('sales.detail', pedido_id=pedido.id))

    producto = Producto.query.get_or_404(producto_id)
    item = PedidoItem(
        pedido_id=pedido.id,
        producto_id=producto.id,
        cantidad=cantidad,
        precio_unitario_cop=producto.precio_venta_cop,
        subtotal_cop=producto.precio_venta_cop * cantidad,
    )
    db.session.add(item)
    db.session.commit()
    flash(f'{producto.nombre} x{cantidad} agregado al pedido.', 'success')
    return redirect(url_for('sales.detail', pedido_id=pedido.id))


# ──────────────────────────────────────────────
#  QUITAR ITEM DEL PEDIDO
# ──────────────────────────────────────────────
@sales_bp.route('/<int:pedido_id>/remove_item/<int:item_id>', methods=['POST'])
@login_required
@role_required('admin', 'employee')
def remove_item(pedido_id, item_id):
    pedido = Pedido.query.get_or_404(pedido_id)
    if pedido.estado != 'abierto':
        flash('Solo se pueden quitar items de un pedido abierto.', 'warning')
        return redirect(url_for('sales.detail', pedido_id=pedido.id))

    item = PedidoItem.query.get_or_404(item_id)
    if item.pedido_id != pedido.id:
        flash('El item no pertenece a este pedido.', 'warning')
        return redirect(url_for('sales.detail', pedido_id=pedido.id))

    db.session.delete(item)
    db.session.commit()
    flash(f'{item.producto.nombre} quitado del pedido.', 'success')
    return redirect(url_for('sales.detail', pedido_id=pedido.id))


# ──────────────────────────────────────────────
#  FORMULARIO DE CIERRE / PAGO
# ──────────────────────────────────────────────
@sales_bp.route('/<int:pedido_id>/close_form', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'employee')
def close_pedido_form(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)
    total_cop = sum(item.subtotal_cop for item in pedido.items)

    if pedido.estado != 'abierto':
        flash('El pedido ya fue pagado o anulado.', 'warning')
        return redirect(url_for('sales.detail', pedido_id=pedido.id))

    if request.method == 'POST':
        moneda_pago = request.form.get('moneda_pago')
        metodo_pago = request.form.get('metodo_pago')
        observaciones = request.form.get('observaciones', '').strip()

        if not moneda_pago or not metodo_pago:
            flash('Selecciona la moneda y el método de pago.', 'warning')
            return redirect(url_for('sales.close_pedido_form', pedido_id=pedido.id))

        # ── Guardar datos del pago ──
        now = datetime.utcnow()
        pedido.total = total_cop
        pedido.moneda_pago = moneda_pago
        pedido.metodo_pago = metodo_pago
        pedido.observaciones = observaciones if observaciones else None
        pedido.estado = 'pagado'
        pedido.pagado_en = now

        # ── Liberar ubicación ──
        ubicacion = pedido.ubicacion
        ubicacion.estado = 'libre'
        ubicacion.fecha_apertura = None

        # ── Descontar inventario (Fase 4: por Receta o fallback insumo_id) ──
        stock_issues = []
        for item in pedido.items:
            if not item.producto.descuenta_inventario:
                continue

            # Prioridad 1: descontar por Recetas (cantidad_gramos × cantidad vendida)
            recetas = Receta.query.filter_by(producto_id=item.producto.id).all()
            if recetas:
                for receta in recetas:
                    insumo = receta.insumo
                    if not insumo:
                        continue
                    # Convertir gramos a la unidad del insumo
                    if insumo.unidad_medida == 'g':
                        cantidad_a_descontar = int(receta.cantidad_gramos * item.cantidad)
                    elif insumo.unidad_medida == 'kg':
                        cantidad_a_descontar = int((receta.cantidad_gramos * item.cantidad) / 1000)
                    elif insumo.unidad_medida == 'ml':
                        cantidad_a_descontar = int(receta.cantidad_gramos * item.cantidad)
                    elif insumo.unidad_medida == 'l':
                        cantidad_a_descontar = int((receta.cantidad_gramos * item.cantidad) / 1000)
                    elif insumo.unidad_medida == 'unidad':
                        cantidad_a_descontar = int(item.cantidad)  # 1 unidad por producto vendido
                    else:
                        cantidad_a_descontar = int(receta.cantidad_gramos * item.cantidad)

                    if cantidad_a_descontar <= 0:
                        continue

                    if insumo.stock_actual >= cantidad_a_descontar:
                        insumo.stock_actual -= cantidad_a_descontar
                        mov = MovimientoInventario(
                            insumo_id=insumo.id,
                            tipo='salida',
                            cantidad=cantidad_a_descontar,
                            costo_total=0,
                            motivo=f'Venta Pedido #{pedido.id} — {item.producto.nombre} x{item.cantidad} (Receta: {receta.cantidad_gramos}g/{insumo.unidad_medida})',
                        )
                        db.session.add(mov)
                    else:
                        stock_issues.append(
                            f'{insumo.nombre}: necesario {cantidad_a_descontar} {insumo.unidad_medida}, disponible {insumo.stock_actual} {insumo.unidad_medida}'
                        )

            # Prioridad 2: fallback a insumo_id directo (comportamiento pre-Fase 4)
            elif item.producto.insumo_id:
                insumo = item.producto.insumo
                if insumo:
                    cantidad_a_descontar = item.cantidad
                    if insumo.stock_actual >= cantidad_a_descontar:
                        insumo.stock_actual -= cantidad_a_descontar
                        mov = MovimientoInventario(
                            insumo_id=insumo.id,
                            tipo='salida',
                            cantidad=cantidad_a_descontar,
                            costo_total=0,
                            motivo=f'Venta Pedido #{pedido.id} — {item.producto.nombre} x{item.cantidad} (fallback insumo_id)',
                        )
                        db.session.add(mov)
                    else:
                        stock_issues.append(
                            f'{insumo.nombre}: necesario {cantidad_a_descontar} {insumo.unidad_medida}, disponible {insumo.stock_actual} {insumo.unidad_medida}'
                        )

        db.session.commit()

        # Mostrar advertencias de stock insuficiente (no bloqueante)
        msg = f'Pedido #{pedido.id} pagado. Ubicación liberada.'
        if stock_issues:
            msg += ' Stock insuficiente para descontar: ' + '; '.join(stock_issues)
            flash(msg, 'warning')
        else:
            flash(msg, 'success')
        return redirect(url_for('sales.detail', pedido_id=pedido.id))

    return render_template(
        'sales/close_form.html',
        pedido=pedido,
        total_cop=total_cop,
    )


# ──────────────────────────────────────────────
#  ANULAR PEDIDO (solo admin)
# ──────────────────────────────────────────────
@sales_bp.route('/<int:pedido_id>/cancel', methods=['POST'])
@login_required
@role_required('admin')
def cancel_pedido(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)

    if pedido.estado != 'abierto':
        flash('Solo se pueden anular pedidos abiertos.', 'warning')
        return redirect(url_for('sales.detail', pedido_id=pedido.id))

    # Anular lógicamente los items que NO han sido eliminados físicamente
    # (los items eliminados físicamente ya no existen en la BD)
    now = datetime.utcnow()
    for item in pedido.items:
        if not item.anulado:
            item.anulado_en = now
            item.motivo_anulacion = 'Anulación de pedido completo'

    pedido.estado = 'anulado'

    # Liberar la ubicación
    ubicacion = pedido.ubicacion
    ubicacion.estado = 'libre'
    ubicacion.fecha_apertura = None

    db.session.commit()
    flash(f'Pedido #{pedido.id} anulado. {len(pedido.items)} items registrados como anulados. Ubicación liberada.', 'info')
    return redirect(url_for('sales.pos_ubicacion', ubicacion_id=ubicacion.id))


# ══════════════════════════════════════════════════
#  POS — PUNTO DE VENTA
# ══════════════════════════════════════════════════

# ──────────────────────────────────────────────
#  POS: PANTALLA PRINCIPAL (selección de espacio)
# ──────────────────────────────────────────────
@sales_bp.route('/pos')
@login_required
@role_required('admin', 'employee')
def pos_index():
    """Muestra el mapa de espacios para seleccionar uno y operar."""
    ubicaciones = Ubicacion.query.order_by(Ubicacion.tipo, Ubicacion.nombre).all()
    return render_template('sales/pos.html', ubicaciones=ubicaciones,
                           ubicacion_selected=None, pedido=None,
                           productos=None, total_cop=0)


# ──────────────────────────────────────────────
#  POS: OPERAR SOBRE UN ESPACIO
# ──────────────────────────────────────────────
@sales_bp.route('/pos/<int:ubicacion_id>')
@login_required
@role_required('admin', 'employee')
def pos_ubicacion(ubicacion_id):
    ubicacion = Ubicacion.query.get_or_404(ubicacion_id)
    productos = Producto.query.order_by(Producto.categoria, Producto.nombre).all()

    # Buscar pedido abierto o crear uno nuevo
    pedido_abierto = Pedido.query.filter_by(
        ubicacion_id=ubicacion.id, estado='abierto'
    ).first()

    if not pedido_abierto:
        # Si está marcada como ocupada pero no hay pedido, forzar libre
        if ubicacion.estado == 'ocupada':
            ubicacion.estado = 'libre'
            ubicacion.fecha_apertura = None
            db.session.commit()

    all_ubicaciones = Ubicacion.query.order_by(Ubicacion.tipo, Ubicacion.nombre).all()

    # Si hay pedido abierto, calcular total
    total_cop = 0
    if pedido_abierto:
        total_cop = sum(
            item.subtotal_cop for item in pedido_abierto.items
            if not item.anulado
        )

    return render_template('sales/pos.html',
                           ubicaciones=all_ubicaciones,
                           ubicacion_selected=ubicacion,
                           pedido=pedido_abierto,
                           productos=productos,
                           total_cop=total_cop)


# ──────────────────────────────────────────────
#  POS: ABRIR NUEVO PEDIDO
# ──────────────────────────────────────────────
@sales_bp.route('/pos/<int:ubicacion_id>/open', methods=['POST'])
@login_required
@role_required('admin', 'employee')
def pos_open(ubicacion_id):
    ubicacion = Ubicacion.query.get_or_404(ubicacion_id)

    if ubicacion.estado != 'libre':
        flash(f'{ubicacion.nombre} no está disponible.', 'warning')
        return redirect(url_for('sales.pos_ubicacion', ubicacion_id=ubicacion.id))

    pedido_existente = Pedido.query.filter_by(
        ubicacion_id=ubicacion.id, estado='abierto'
    ).first()
    if pedido_existente:
        return redirect(url_for('sales.pos_ubicacion', ubicacion_id=ubicacion.id))

    ubicacion.estado = 'ocupada'
    ubicacion.fecha_apertura = datetime.utcnow()

    pedido = Pedido(ubicacion_id=ubicacion.id, total=0)
    db.session.add(pedido)
    db.session.commit()

    return redirect(url_for('sales.pos_ubicacion', ubicacion_id=ubicacion.id))


# ──────────────────────────────────────────────
#  POS: AGREGAR ITEM RÁPIDO
# ──────────────────────────────────────────────
@sales_bp.route('/<int:pedido_id>/quick_add/<int:producto_id>', methods=['POST'])
@login_required
@role_required('admin', 'employee')
def quick_add(pedido_id, producto_id):
    pedido = Pedido.query.get_or_404(pedido_id)
    if pedido.estado != 'abierto':
        flash('Solo se pueden agregar items a un pedido abierto.', 'warning')
        return redirect(url_for('sales.pos_ubicacion', ubicacion_id=pedido.ubicacion_id))

    producto = Producto.query.get_or_404(producto_id)
    cantidad = request.form.get('cantidad', 1, type=int)
    if cantidad <= 0:
        cantidad = 1

    # Buscar si ya existe el mismo producto NO anulado en el pedido
    item_existente = PedidoItem.query.filter_by(
        pedido_id=pedido.id,
        producto_id=producto.id,
        anulado_en=None
    ).first()

    if item_existente:
        # Incrementar cantidad
        item_existente.cantidad += cantidad
        item_existente.subtotal_cop = item_existente.precio_unitario_cop * item_existente.cantidad
    else:
        item = PedidoItem(
            pedido_id=pedido.id,
            producto_id=producto.id,
            cantidad=cantidad,
            precio_unitario_cop=producto.precio_venta_cop,
            subtotal_cop=producto.precio_venta_cop * cantidad,
        )
        db.session.add(item)

    db.session.commit()

    # Si la petición es AJAX, devolver JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        items_data = []
        for item in pedido.items:
            if not item.anulado:
                items_data.append({
                    'id': item.id,
                    'producto': item.producto.nombre,
                    'cantidad': item.cantidad,
                    'precio_unitario': item.precio_unitario_cop,
                    'subtotal': item.subtotal_cop,
                })
        total = sum(i['subtotal'] for i in items_data)
        return jsonify({'items': items_data, 'total': total, 'ok': True})

    return redirect(url_for('sales.pos_ubicacion', ubicacion_id=pedido.ubicacion_id))


# ──────────────────────────────────────────────
#  POS: QUITAR ITEM (solo pedido abierto — eliminación física)
# ──────────────────────────────────────────────
@sales_bp.route('/<int:pedido_id>/quick_remove/<int:item_id>', methods=['POST'])
@login_required
@role_required('admin', 'employee')
def quick_remove(pedido_id, item_id):
    pedido = Pedido.query.get_or_404(pedido_id)
    if pedido.estado != 'abierto':
        flash('Solo se pueden quitar items de un pedido abierto.', 'warning')
        return redirect(url_for('sales.pos_ubicacion', ubicacion_id=pedido.ubicacion_id))

    item = PedidoItem.query.get_or_404(item_id)
    if item.pedido_id != pedido.id:
        flash('El item no pertenece a este pedido.', 'warning')
        return redirect(url_for('sales.pos_ubicacion', ubicacion_id=pedido.ubicacion_id))

    # Disminuir cantidad o eliminar si queda en 0
    if item.cantidad > 1:
        item.cantidad -= 1
        item.subtotal_cop = item.precio_unitario_cop * item.cantidad
    else:
        db.session.delete(item)

    db.session.commit()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        items_data = []
        for i in pedido.items:
            if not i.anulado:
                items_data.append({
                    'id': i.id,
                    'producto': i.producto.nombre,
                    'cantidad': i.cantidad,
                    'precio_unitario': i.precio_unitario_cop,
                    'subtotal': i.subtotal_cop,
                })
        total = sum(i['subtotal'] for i in items_data)
        return jsonify({'items': items_data, 'total': total, 'ok': True})

    return redirect(url_for('sales.pos_ubicacion', ubicacion_id=pedido.ubicacion_id))


# ──────────────────────────────────────────────
#  ANULAR ITEM (solo pedido pagado — anulación lógica)
#  NO elimina físicamente; marca anulado_en.
# ──────────────────────────────────────────────
@sales_bp.route('/<int:pedido_id>/void_item/<int:item_id>', methods=['POST'])
@login_required
@role_required('admin')
def void_item(pedido_id, item_id):
    """Anular un item de un pedido ya pagado (solo admin).
    El item NO se borra de la BD, se marca como anulado."""
    pedido = Pedido.query.get_or_404(pedido_id)
    if pedido.estado != 'pagado':
        flash('Solo se pueden anular items de pedidos pagados.', 'warning')
        return redirect(url_for('sales.detail', pedido_id=pedido.id))

    item = PedidoItem.query.get_or_404(item_id)
    if item.pedido_id != pedido.id:
        flash('El item no pertenece a este pedido.', 'warning')
        return redirect(url_for('sales.detail', pedido_id=pedido.id))

    if item.anulado:
        flash('Este item ya fue anulado.', 'warning')
        return redirect(url_for('sales.detail', pedido_id=pedido.id))

    ahora = datetime.utcnow()
    item.anulado_en = ahora
    item.motivo_anulacion = request.form.get('motivo', 'Anulado por administrador')

    db.session.commit()
    flash(f'{item.producto.nombre} x{item.cantidad} anulado.', 'info')
    return redirect(url_for('sales.detail', pedido_id=pedido.id))


# ──────────────────────────────────────────────
#  RESTAURAR ITEM ANULADO (solo admin)
# ──────────────────────────────────────────────
@sales_bp.route('/<int:pedido_id>/restore_item/<int:item_id>', methods=['POST'])
@login_required
@role_required('admin')
def restore_item(pedido_id, item_id):
    pedido = Pedido.query.get_or_404(pedido_id)
    item = PedidoItem.query.get_or_404(item_id)

    if item.pedido_id != pedido.id:
        flash('El item no pertenece a este pedido.', 'warning')
        return redirect(url_for('sales.detail', pedido_id=pedido.id))

    if not item.anulado:
        flash('Este item no está anulado.', 'warning')
        return redirect(url_for('sales.detail', pedido_id=pedido.id))

    item.anulado_en = None
    item.motivo_anulacion = None

    db.session.commit()
    flash(f'{item.producto.nombre} x{item.cantidad} restaurado.', 'success')
    return redirect(url_for('sales.detail', pedido_id=pedido.id))
