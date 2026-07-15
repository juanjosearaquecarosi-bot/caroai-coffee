from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from ..models import db, Mesa
from datetime import datetime

tables_bp = Blueprint('tables', __name__)

@tables_bp.route('/')
@login_required
def index():
    mesas = Mesa.query.order_by(Mesa.numero).all()
    return render_template('tables/index.html', mesas=mesas)

@login_required
@tables_bp.route('/open/<int:mesa_id>', methods=['POST'])
def open_mesa(mesa_id):
    mesa = Mesa.query.get_or_404(mesa_id)
    if mesa.estado == 'libre':
        mesa.estado = 'ocupada'
        mesa.fecha_apertura = datetime.utcnow()
        db.session.commit()
        flash(f'Mesa {mesa.numero} abierta.', 'success')
    else:
        flash('La mesa no está disponible.', 'warning')
    return redirect(url_for('tables.index'))

@login_required
@tables_bp.route('/close/<int:mesa_id>', methods=['POST'])
def close_mesa(mesa_id):
    mesa = Mesa.query.get_or_404(mesa_id)
    if mesa.estado == 'ocupada':
        mesa.estado = 'cerrada'
        mesa.fecha_cierre = datetime.utcnow()
        db.session.commit()
        flash(f'Mesa {mesa.numero} cerrada.', 'success')
    else:
        flash('La mesa no está abierta.', 'warning')
    return redirect(url_for('tables.index'))

@login_required
@tables_bp.route('/reset/<int:mesa_id>', methods=['POST'])
def reset_mesa(mesa_id):
    mesa = Mesa.query.get_or_404(mesa_id)
    if mesa.estado == 'cerrada':
        mesa.estado = 'libre'
        mesa.fecha_apertura = None
        mesa.fecha_cierre = None
        db.session.commit()
        flash(f'Mesa {mesa.numero} reiniciada.', 'success')
    else:
        flash('Solo se puede reiniciar una mesa cerrada.', 'warning')
    return redirect(url_for('tables.index'))