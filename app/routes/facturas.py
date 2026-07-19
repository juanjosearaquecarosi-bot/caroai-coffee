from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from ..models import db, Factura
from ..utils.decorators import role_required
from datetime import date, datetime, timedelta

facturas_bp = Blueprint('facturas', __name__)


# ──────────────────────────────────────────────
#  LISTAR FACTURAS (admin only)
#  Separa en pendientes y pagadas.
#  Muestra alerta si hay facturas próximas a vencer.
# ──────────────────────────────────────────────
@facturas_bp.route('/')
@login_required
@role_required('admin')
def index():
    pendientes = Factura.query.filter_by(estado='pendiente').order_by(
        Factura.fecha_vencimiento.asc()
    ).all()
    pagadas = Factura.query.filter_by(estado='pagada').order_by(
        Factura.fecha_pago.desc()
    ).all()

    # Detectar próximas a vencer (2 días por defecto)
    hoy = date.today()
    umbral = request.args.get('dias', 2, type=int)
    fecha_limite = hoy + timedelta(days=umbral)
    por_vencer = [
        f for f in pendientes
        if f.fecha_vencimiento <= fecha_limite
    ]

    return render_template(
        'facturas/index.html',
        pendientes=pendientes,
        pagadas=pagadas,
        por_vencer=por_vencer,
        umbral=umbral,
        hoy=hoy,
        fecha_limite=fecha_limite,
    )


# ──────────────────────────────────────────────
#  CREAR FACTURA (admin only)
# ──────────────────────────────────────────────
@facturas_bp.route('/nueva', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def nueva():
    if request.method == 'POST':
        referencia = request.form.get('referencia', '').strip()
        empresa = request.form.get('empresa', '').strip()
        fecha_recibida_str = request.form.get('fecha_recibida', '').strip()
        dias_credito = request.form.get('dias_credito', type=int, default=0)
        monto = request.form.get('monto', type=int)
        notas = request.form.get('notas', '').strip()

        if not referencia or not empresa or not fecha_recibida_str:
            flash('Completa los campos obligatorios: referencia, empresa y fecha recibida.', 'warning')
            return redirect(url_for('facturas.nueva'))

        if dias_credito is None or dias_credito < 0:
            dias_credito = 0

        try:
            fecha_recibida = date.fromisoformat(fecha_recibida_str)
        except ValueError:
            flash('Fecha inválida. Usa el formato AAAA-MM-DD.', 'warning')
            return redirect(url_for('facturas.nueva'))

        # Verificar referencia única
        existente = Factura.query.filter_by(referencia=referencia).first()
        if existente:
            flash(f'Ya existe una factura con la referencia "{referencia}".', 'warning')
            return redirect(url_for('facturas.nueva'))

        # Calcular fecha de vencimiento
        fecha_vencimiento = fecha_recibida + timedelta(days=dias_credito)

        factura = Factura(
            referencia=referencia,
            empresa=empresa,
            fecha_recibida=fecha_recibida,
            dias_credito=dias_credito,
            fecha_vencimiento=fecha_vencimiento,
            estado='pendiente',
            monto=monto if monto and monto > 0 else None,
            notas=notas if notas else None,
        )
        db.session.add(factura)
        db.session.commit()
        flash(f'Factura {referencia} de {empresa} registrada. Vence {fecha_vencimiento.strftime("%d/%m/%Y")}.', 'success')
        return redirect(url_for('facturas.index'))

    return render_template('facturas/index.html', show_form=True, hoy=date.today())


# ──────────────────────────────────────────────
#  MARCAR COMO PAGADA (admin only)
# ──────────────────────────────────────────────
@facturas_bp.route('/<int:id>/pagar', methods=['POST'])
@login_required
@role_required('admin')
def pagar(id):
    factura = Factura.query.get_or_404(id)

    if factura.estado != 'pendiente':
        flash(f'La factura {factura.referencia} ya fue pagada.', 'warning')
        return redirect(url_for('facturas.index'))

    hoy = date.today()
    factura.estado = 'pagada'
    factura.fecha_pago = hoy
    db.session.commit()
    flash(f'Factura {factura.referencia} de {factura.empresa} marcada como pagada.', 'success')
    return redirect(url_for('facturas.index'))


# ──────────────────────────────────────────────
#  LISTAR PRÓXIMAS A VENCER (admin only)
#  JSON para notificaciones o integraciones
# ──────────────────────────────────────────────
@facturas_bp.route('/por_vencer')
@login_required
@role_required('admin')
def por_vencer():
    hoy = date.today()
    umbral = request.args.get('dias', 2, type=int)
    fecha_limite = hoy + timedelta(days=umbral)

    facturas = Factura.query.filter(
        Factura.estado == 'pendiente',
        Factura.fecha_vencimiento <= fecha_limite,
    ).order_by(Factura.fecha_vencimiento.asc()).all()

    return render_template(
        'facturas/index.html',
        pendientes=Factura.query.filter_by(estado='pendiente').order_by(Factura.fecha_vencimiento.asc()).all(),
        pagadas=Factura.query.filter_by(estado='pagada').order_by(Factura.fecha_pago.desc()).all(),
        por_vencer=facturas,
        umbral=umbral,
        hoy=hoy,
        fecha_limite=fecha_limite,
        filtro_por_vencer=True,
    )
