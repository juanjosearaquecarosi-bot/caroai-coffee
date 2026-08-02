from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from ..models import db, Nota, Mesa, Pedido
from ..utils.decorators import role_required

notas_bp = Blueprint('notas', __name__, url_prefix='/notas')


# ──────────────────────────────────────────────
#  LISTAR NOTAS (admin only)
#  Muestra separadas: deudas pendientes, notas generales, deudas cobradas
# ──────────────────────────────────────────────
@notas_bp.route('/')
@login_required
@role_required('admin')
def index():
    deudas_pendientes = Nota.query.filter_by(tipo='deuda', estado='pendiente').order_by(
        Nota.creado_en.desc()
    ).all()

    deudas_cobradas = Nota.query.filter_by(tipo='deuda', estado='cobrada').order_by(
        Nota.creado_en.desc()
    ).all()

    notas_generales = Nota.query.filter_by(tipo='general').order_by(
        Nota.creado_en.desc()
    ).all()

    return render_template(
        'notas/index.html',
        deudas_pendientes=deudas_pendientes,
        deudas_cobradas=deudas_cobradas,
        notas_generales=notas_generales,
    )


# ──────────────────────────────────────────────
#  CREAR NOTA (admin only)
# ──────────────────────────────────────────────
@notas_bp.route('/nueva', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def nueva():
    mesas = Mesa.query.order_by(Mesa.id).all()

    if request.method == 'POST':
        titulo = request.form.get('titulo', '').strip()
        contenido = request.form.get('contenido', '').strip()
        tipo = request.form.get('tipo', 'general')
        cliente = request.form.get('cliente', '').strip() or None
        mesa_id = request.form.get('mesa_id', type=int)
        monto_cop = request.form.get('monto_cop', type=int)
        pedido_id = request.form.get('pedido_id', type=int)

        if not titulo:
            flash('El título es obligatorio.', 'warning')
            return render_template('notas/index.html', show_form=True, mesas=mesas,
                                   deudas_pendientes=[], deudas_cobradas=[], notas_generales=[])

        if tipo == 'deuda' and (not monto_cop or monto_cop <= 0):
            flash('Para una deuda, el monto es obligatorio y debe ser mayor a 0.', 'warning')
            return render_template('notas/index.html', show_form=True, mesas=mesas,
                                   deudas_pendientes=[], deudas_cobradas=[], notas_generales=[])

        if mesa_id and not db.session.get(Mesa, mesa_id):
            mesa_id = None

        if pedido_id and not db.session.get(Pedido, pedido_id):
            pedido_id = None

        nota = Nota(
            titulo=titulo,
            contenido=contenido if contenido else None,
            tipo=tipo,
            cliente=cliente,
            mesa_id=mesa_id,
            monto_cop=monto_cop if monto_cop and monto_cop > 0 else None,
            pedido_id=pedido_id,
            estado='pendiente' if tipo == 'deuda' else 'general',
        )
        db.session.add(nota)
        db.session.commit()

        if tipo == 'deuda':
            flash(f'💰 Deuda registrada: {titulo} · ${monto_cop:,} COP', 'success')
        else:
            flash(f'📝 Nota guardada: {titulo}', 'success')

        return redirect(url_for('notas.index'))

    return render_template('notas/index.html', show_form=True, mesas=mesas,
                           deudas_pendientes=[], deudas_cobradas=[], notas_generales=[])


# ──────────────────────────────────────────────
#  MARCAR DEUDA COMO COBRADA (admin only)
# ──────────────────────────────────────────────
@notas_bp.route('/<int:id>/cobrar', methods=['POST'])
@login_required
@role_required('admin')
def cobrar(id):
    nota = db.session.get(Nota, id)
    if not nota:
        flash('Nota no encontrada.', 'danger')
        return redirect(url_for('notas.index'))

    if nota.tipo != 'deuda':
        flash('Solo se pueden cobrar notas de tipo deuda.', 'warning')
        return redirect(url_for('notas.index'))

    if nota.estado == 'cobrada':
        flash(f'La deuda «{nota.titulo}» ya fue cobrada.', 'info')
        return redirect(url_for('notas.index'))

    nota.estado = 'cobrada'
    db.session.commit()

    monto_str = f' · ${nota.monto_cop:,} COP' if nota.monto_cop else ''
    flash(f'✅ Deuda cobrada: {nota.titulo}{monto_str}', 'success')
    return redirect(url_for('notas.index'))


# ──────────────────────────────────────────────
#  ELIMINAR NOTA (admin only)
# ──────────────────────────────────────────────
@notas_bp.route('/<int:id>/eliminar', methods=['POST'])
@login_required
@role_required('admin')
def eliminar(id):
    nota = db.session.get(Nota, id)
    if not nota:
        flash('Nota no encontrada.', 'danger')
        return redirect(url_for('notas.index'))

    db.session.delete(nota)
    db.session.commit()

    flash(f'🗑️ Nota «{nota.titulo}» eliminada.', 'info')
    return redirect(url_for('notas.index'))
