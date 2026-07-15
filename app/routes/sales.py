from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from ..models import db, Mesa, Pedido, Producto, PedidoItem, TasaCambio
from datetime import datetime

sales_bp = Blueprint('sales', __name__)

@login_required
@sales_bp.route('/')
def index():
    pedidos = Pedido.query.order_by(Pedido.fecha_hora.desc()).all()
    return render_template('sales/index.html', pedidos=pedidos)

@login_required
@sales_bp.route('/create/<int:mesa_id>', methods=['POST'])
def create_pedido(mesa_id):
    mesa = Mesa.query.get_or_404(mesa_id)
    if mesa.estado != 'ocupada':
        flash('La mesa debe estar abierta para crear un pedido.', 'warning')
        return redirect(url_for('tables.index'))
    # Check if there's already an open pedido for this mesa
    open_pedido = Pedido.query.filter_by(mesa_id=mesa.id, estado='abierto').first()
    if open_pedido:
        flash('Ya existe un pedido abierto para esta mesa.', 'warning')
        return redirect(url_for('sales.detail', pedido_id=open_pedido.id))
    # Create a new pedido (we'll need to get a tasa for today, but for now we can use a default)
    today = datetime.utcnow().date()
    tasa = TasaCambio.query.filter_by(fecha=today).first()
    if not tasa:
        # Create a default tasa (should be configured by the user)
        tasa = TasaCambio(
            fecha=today,
            tasa_cop_usd=3600.0,  # default, should be configurable
            tasa_tienda_bs_usd=4.5   # default, should be configurable
        )
        db.session.add(tasa)
        db.session.commit()
    pedido = Pedido(
        mesa_id=mesa.id,
        moneda_recibida='COP',  # default, will be updated when closing
        monto_recibido=0,
        tasa_id=tasa.id
    )
    db.session.add(pedido)
    db.session.commit()
    flash('Pedido creado.', 'success')
    return redirect(url_for('sales.detail', pedido_id=pedido.id))

@login_required
@sales_bp.route('/<int:pedido_id>')
def detail(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)
    productos = Producto.query.order_by(Producto.nombre).all()
    return render_template('sales/detail.html', pedido=pedido, productos=productos)

@login_required
@sales_bp.route('/<int:pedido_id>/add_item', methods=['POST'])
def add_item(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)
    if pedido.estado != 'abierto':
        flash('Solo se pueden agregar items a un pedido abierto.', 'warning')
        return redirect(url_for('sales.detail', pedido_id=pedido.id))
    producto_id = request.form.get('producto_id')
    cantidad = request.form.get('cantidad', type=int, default=1)
    if not producto_id or cantidad <= 0:
        flash('Datos de producto o cantidad inválidos.', 'warning')
        return redirect(url_for('sales.detail', pedido_id=pedido.id))
    producto = Producto.query.get_or_404(producto_id)
    # Create pedido_item
    pedido_item = PedidoItem(
        pedido_id=pedido.id,
        producto_id=producto.id,
        cantidad=cantidad,
        precio_unitario_cop=producto.precio_venta_cop,
        subtotal_cop=producto.precio_venta_cop * cantidad
    )
    db.session.add(pedido_item)
    # Update pedido monto_recibido? We'll update when closing based on moneda_recibida.
    # For now, we just add the item.
    db.session.commit()
    flash('Item agregado al pedido.', 'success')
    return redirect(url_for('sales.detail', pedido_id=pedido.id))

@login_required
@sales_bp.route('/<int:pedido_id>/remove_item/<int:item_id>', methods=['POST'])
def remove_item(pedido_id, item_id):
    pedido = Pedido.query.get_or_404(pedido_id)
    if pedido.estado != 'abierto':
        flash('Solo se pueden eliminar items de un pedido abierto.', 'warning')
        return redirect(url_for('sales.detail', pedido_id=pedido.id))
    item = PedidoItem.query.get_or_404(item_id)
    if item.pedido_id != pedido.id:
        flash('Item no pertenece a este pedido.', 'warning')
        return redirect(url_for('sales.detail', pedido_id=pedido.id))
    db.session.delete(item)
    db.session.commit()
    flash('Item eliminado del pedido.', 'success')
    return redirect(url_for('sales.detail', pedido_id=pedido.id))

@login_required
@sales_bp.route('/<int:pedido_id>/close', methods=['POST'])
def close_pedido(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)
    if pedido.estado != 'abierto':
        flash('El pedido ya está cerrado.', 'warning')
        return redirect(url_for('sales.detail', pedido_id=pedido.id))
    # Here we would calculate the total in the selected moneda and update monto_recibido
    # For simplicity, we'll just set the estado to cerrado and ask the user to input the monto via a form?
    # But the spec says we need to record the moneda_recibida and monto_recibido.
    # We'll redirect to a form where the user selects the moneda and enters the monto received.
    return redirect(url_for('sales.close_pedido_form', pedido_id=pedido.id))

@login_required
@sales_bp.route('/<int:pedido_id>/close_form', methods=['GET', 'POST'])
def close_pedido_form(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)
    if request.method == 'POST':
        moneda_recibida = request.form.get('moneda_recibida')
        monto_recibido = request.form.get('monto_recibido', type=int)
        if not moneda_recibida or monto_recibido is None or monto_recibido <= 0:
            flash('Por favor, seleccione la moneda e ingrese el monto recibido.', 'warning')
            return redirect(url_for('sales.close_pedido_form', pedido_id=pedido.id))
        pedido.moneda_recibida = moneda_recibida
        pedido.monto_recibido = monto_recibido
        pedido.estado = 'cerrado'
        # Also close the associated mesa
        mesa = pedido.mesa
        mesa.estado = 'cerrada'
        mesa.fecha_cierre = datetime.utcnow()
        db.session.commit()
        flash('Pedido cerrado y mesa actualizada.', 'success')
        return redirect(url_for('tables.index'))
    return render_template('sales/close_form.html', pedido=pedido)