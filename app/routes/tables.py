from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from ..models import db, Ubicacion, Pedido
from ..utils.decorators import role_required
from datetime import datetime

tables_bp = Blueprint('tables', __name__)


@tables_bp.route('/')
@login_required
@role_required('admin', 'employee')
def index():
    ubicaciones = Ubicacion.query.order_by(Ubicacion.tipo, Ubicacion.nombre).all()
    return render_template('tables/index.html', ubicaciones=ubicaciones)


@tables_bp.route('/open/<int:ubicacion_id>', methods=['POST'])
@login_required
@role_required('admin', 'employee')
def open_ubicacion(ubicacion_id):
    ubicacion = Ubicacion.query.get_or_404(ubicacion_id)

    if ubicacion.estado != 'libre':
        flash(f'{ubicacion.nombre} no está disponible.', 'warning')
        return redirect(url_for('tables.index'))

    # Verificar que no haya un pedido abierto (regla: 1 ubicación = 1 cuenta)
    pedido_existente = Pedido.query.filter_by(
        ubicacion_id=ubicacion.id, estado='abierto'
    ).first()
    if pedido_existente:
        flash(f'{ubicacion.nombre} ya tiene un pedido abierto.', 'warning')
        return redirect(url_for('sales.detail', pedido_id=pedido_existente.id))

    # Marcar como ocupada y crear pedido
    ubicacion.estado = 'ocupada'
    ubicacion.fecha_apertura = datetime.utcnow()

    pedido = Pedido(
        ubicacion_id=ubicacion.id,
        total=0,
    )
    db.session.add(pedido)
    db.session.commit()

    flash(f'{ubicacion.nombre} abierta. Pedido #{pedido.id} creado.', 'success')
    return redirect(url_for('sales.detail', pedido_id=pedido.id))
