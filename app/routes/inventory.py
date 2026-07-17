from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from ..models import db, Insumo, MovimientoInventario
from ..utils.decorators import role_required
from datetime import datetime

inventory_bp = Blueprint('inventory', __name__)

@inventory_bp.route('/')
@login_required
@role_required('admin', 'employee')
def index():
    insumos = Insumo.query.order_by(Insumo.nombre).all()
    return render_template('inventory/index.html', insumos=insumos)

@inventory_bp.route('/create', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def create():
    if request.method == 'POST':
        nombre = request.form['nombre']
        unidad_medida = request.form['unidad_medida']
        costo_unitario_cop = int(request.form['costo_unitario_cop'])
        stock_actual = int(request.form['stock_actual'])
        stock_minimo = int(request.form['stock_minimo'])

        insumo = Insumo(
            nombre=nombre,
            unidad_medida=unidad_medida,
            costo_unitario_cop=costo_unitario_cop,
            stock_actual=stock_actual,
            stock_minimo=stock_minimo
        )
        db.session.add(insumo)
        db.session.commit()
        flash(f'Insumo "{nombre}" creado exitosamente.', 'success')
        return redirect(url_for('inventory.index'))

    return render_template('inventory/form.html', insumo=None, action='Crear')

@inventory_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def edit(id):
    insumo = Insumo.query.get_or_404(id)
    if request.method == 'POST':
        insumo.nombre = request.form['nombre']
        insumo.unidad_medida = request.form['unidad_medida']
        insumo.costo_unitario_cop = int(request.form['costo_unitario_cop'])
        insumo.stock_actual = int(request.form['stock_actual'])
        insumo.stock_minimo = int(request.form['stock_minimo'])
        db.session.commit()
        flash(f'Insumo "{insumo.nombre}" actualizado exitosamente.', 'success')
        return redirect(url_for('inventory.index'))

    return render_template('inventory/form.html', insumo=insumo, action='Actualizar')

@inventory_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete(id):
    insumo = Insumo.query.get_or_404(id)
    if insumo.movimientos or insumo.recetas:
        flash(f'No se puede eliminar el insumo "{insumo.nombre}" porque tiene movimientos o recetas asociadas.', 'error')
        return redirect(url_for('inventory.index'))

    db.session.delete(insumo)
    db.session.commit()
    flash(f'Insumo "{insumo.nombre}" eliminado exitosamente.', 'success')
    return redirect(url_for('inventory.index'))

@inventory_bp.route('/<int:id>/movimientos')
@login_required
@role_required('admin', 'employee')
def movimientos(id):
    insumo = Insumo.query.get_or_404(id)
    movimientos = MovimientoInventario.query.filter_by(insumo_id=id).order_by(MovimientoInventario.fecha.desc()).all()
    return render_template('inventory/movimientos.html', insumo=insumo, movimientos=movimientos)

@inventory_bp.route('/<int:id>/movimiento/nuevo', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'employee')
def nuevo_movimiento(id):
    insumo = Insumo.query.get_or_404(id)
    if request.method == 'POST':
        tipo = request.form['tipo']
        cantidad = int(request.form['cantidad'])
        motivo = request.form['motivo']

        costo_total = 0
        if tipo == 'entrada':
            costo_total = cantidad * insumo.costo_unitario_cop
        else:
            costo_total = 0

        fecha_str = request.form.get('fecha')
        if fecha_str:
            try:
                fecha = datetime.fromisoformat(fecha_str)
            except ValueError:
                fecha = datetime.utcnow()
        else:
            fecha = datetime.utcnow()

        movimiento = MovimientoInventario(
            insumo_id=id,
            tipo=tipo,
            cantidad=cantidad,
            costo_total=costo_total,
            motivo=motivo,
            fecha=fecha
        )

        if tipo == 'entrada':
            insumo.stock_actual += cantidad
        elif tipo in ['salida', 'merma']:
            if insumo.stock_actual < cantidad:
                flash(f'No hay suficiente stock de {insumo.nombre}. Disponible: {insumo.stock_actual} {insumo.unidad_medida}, necesario: {cantidad} {insumo.unidad_medida}', 'error')
                return redirect(url_for('inventory.nuevo_movimiento', id=id))
            insumo.stock_actual -= cantidad
        elif tipo == 'ajuste':
            nuevo_stock = insumo.stock_actual + cantidad
            if nuevo_stock < 0:
                flash(f'El ajuste resultaría en stock negativo para {insumo.nombre}. Stock actual: {insumo.stock_actual} {insumo.unidad_medida}', 'error')
                return redirect(url_for('inventory.nuevo_movimiento', id=id))
            insumo.stock_actual = nuevo_stock

        db.session.add(movimiento)
        db.session.commit()
        flash(f'Movimiento de {tipo} registrado exitosamente.', 'success')
        return redirect(url_for('inventory.movimientos', id=id))

    return render_template('inventory/moviment_form.html', insumo=insumo)
