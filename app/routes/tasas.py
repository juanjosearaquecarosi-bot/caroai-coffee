from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from ..models import db, TasaCambio
from ..utils.decorators import role_required
from datetime import datetime

tasas_bp = Blueprint('tasas', __name__)


# ──────────────────────────────────────────────
#  LISTAR TASAS (admin only)
# ──────────────────────────────────────────────
@tasas_bp.route('/')
@login_required
@role_required('admin')
def index():
    tasas = TasaCambio.query.order_by(TasaCambio.vigente_desde.desc()).all()
    return render_template('tasas/index.html', tasas=tasas)


# ──────────────────────────────────────────────
#  CREAR TASA (admin only)
# ──────────────────────────────────────────────
@tasas_bp.route('/create', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def create():
    if request.method == 'POST':
        moneda_origen = request.form.get('moneda_origen', '').strip()
        moneda_destino = request.form.get('moneda_destino', '').strip()
        tasa = request.form.get('tasa', type=float)
        vigente_desde_str = request.form.get('vigente_desde', '').strip()

        if not moneda_origen or not moneda_destino or not tasa or tasa <= 0:
            flash('Completa todos los campos obligatorios.', 'warning')
            return redirect(url_for('tasas.create'))

        if moneda_origen == moneda_destino:
            flash('La moneda de origen y destino deben ser diferentes.', 'warning')
            return redirect(url_for('tasas.create'))

        try:
            vigente_desde = datetime.fromisoformat(vigente_desde_str) if vigente_desde_str else datetime.utcnow()
        except ValueError:
            flash('Fecha inválida. Usa el formato AAAA-MM-DD o AAAA-MM-DDTHH:MM.', 'warning')
            return redirect(url_for('tasas.create'))

        t = TasaCambio(
            moneda_origen=moneda_origen,
            moneda_destino=moneda_destino,
            tasa=tasa,
            vigente_desde=vigente_desde,
        )
        db.session.add(t)
        db.session.commit()
        flash(f'Tasa creada: 1 {moneda_origen} = {tasa} {moneda_destino}', 'success')
        return redirect(url_for('tasas.index'))

    now_str = datetime.utcnow().strftime('%Y-%m-%dT%H:%M')
    return render_template('tasas/form.html', action='Crear', tasa=None, now_str=now_str)


# ──────────────────────────────────────────────
#  EDITAR TASA (admin only)
# ──────────────────────────────────────────────
@tasas_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def edit(id):
    t = TasaCambio.query.get_or_404(id)

    if request.method == 'POST':
        t.moneda_origen = request.form.get('moneda_origen', '').strip()
        t.moneda_destino = request.form.get('moneda_destino', '').strip()
        t.tasa = request.form.get('tasa', type=float)
        vigente_desde_str = request.form.get('vigente_desde', '').strip()

        if not t.moneda_origen or not t.moneda_destino or not t.tasa or t.tasa <= 0:
            flash('Completa todos los campos obligatorios.', 'warning')
            return redirect(url_for('tasas.edit', id=id))

        if t.moneda_origen == t.moneda_destino:
            flash('La moneda de origen y destino deben ser diferentes.', 'warning')
            return redirect(url_for('tasas.edit', id=id))

        try:
            t.vigente_desde = datetime.fromisoformat(vigente_desde_str) if vigente_desde_str else datetime.utcnow()
        except ValueError:
            flash('Fecha inválida.', 'warning')
            return redirect(url_for('tasas.edit', id=id))

        db.session.commit()
        flash('Tasa actualizada.', 'success')
        return redirect(url_for('tasas.index'))

    now_str = t.vigente_desde.strftime('%Y-%m-%dT%H:%M')
    return render_template('tasas/form.html', action='Editar', tasa=t, now_str=now_str)


# ──────────────────────────────────────────────
#  ELIMINAR TASA (admin only)
# ──────────────────────────────────────────────
@tasas_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete(id):
    t = TasaCambio.query.get_or_404(id)
    db.session.delete(t)
    db.session.commit()
    flash('Tasa eliminada.', 'info')
    return redirect(url_for('tasas.index'))
