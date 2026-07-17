from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from ..models import db, Gasto
from ..utils.decorators import role_required
from datetime import date, datetime

PER_PAGE = 20

gastos_bp = Blueprint('gastos', __name__)


# ──────────────────────────────────────────────
#  LISTAR GASTOS (admin only)
#  Filtros: mes, año, categoría
#  Paginación: 20 por página
# ──────────────────────────────────────────────
@gastos_bp.route('/')
@login_required
@role_required('admin')
def index():
    today = date.today()
    mes = request.args.get('mes', type=int, default=today.month)
    anio = request.args.get('anio', type=int, default=today.year)
    categoria = request.args.get('categoria', '').strip()
    page = request.args.get('page', type=int, default=1)

    # Validar mes/anio
    if mes < 1 or mes > 12:
        mes = today.month
    if anio < 2000 or anio > 2100:
        anio = today.year
    if page < 1:
        page = 1

    # Construir query base
    query = Gasto.query

    # Filtro por mes/año
    month_start = date(anio, mes, 1)
    if mes == 12:
        month_end = date(anio + 1, 1, 1)
    else:
        month_end = date(anio, mes + 1, 1)

    query = query.filter(Gasto.fecha >= month_start, Gasto.fecha < month_end)

    # Filtro por categoría
    if categoria:
        query = query.filter(Gasto.categoria == categoria)

    # Ordenar y paginar
    query = query.order_by(Gasto.fecha.desc(), Gasto.creado_en.desc())
    pagination = query.paginate(page=page, per_page=PER_PAGE, error_out=False)
    gastos = pagination.items

    # Totales del mes filtrado (para el resumen)
    totales_por_moneda = {}
    for g in gastos:
        mon = g.moneda
        totales_por_moneda[mon] = totales_por_moneda.get(mon, 0) + g.monto

    return render_template(
        'gastos/index.html',
        gastos=gastos,
        pagination=pagination,
        mes=mes,
        anio=anio,
        categoria=categoria,
        totales_por_moneda=totales_por_moneda,
        today=today,
    )


# ──────────────────────────────────────────────
#  CREAR GASTO (admin only)
# ──────────────────────────────────────────────
@gastos_bp.route('/create', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def create():
    if request.method == 'POST':
        concepto = request.form.get('concepto', '').strip()
        categoria = request.form.get('categoria', '').strip()
        monto = request.form.get('monto', type=int)
        moneda = request.form.get('moneda', '').strip()
        fecha_str = request.form.get('fecha', '').strip()
        observaciones = request.form.get('observaciones', '').strip()

        if not concepto or not categoria or not moneda or monto is None or monto <= 0:
            flash('Completa todos los campos obligatorios: concepto, categoría, monto y moneda.', 'warning')
            return redirect(url_for('gastos.create'))

        try:
            fecha = date.fromisoformat(fecha_str) if fecha_str else date.today()
        except ValueError:
            flash('Fecha inválida. Usa el formato AAAA-MM-DD.', 'warning')
            return redirect(url_for('gastos.create'))

        gasto = Gasto(
            concepto=concepto,
            categoria=categoria,
            monto=monto,
            moneda=moneda,
            fecha=fecha,
            observaciones=observaciones if observaciones else None,
        )
        db.session.add(gasto)
        db.session.commit()
        flash(f'Gasto registrado: {concepto} — ${monto:,} {moneda}', 'success')
        return redirect(url_for('gastos.index'))

    today = date.today().isoformat()
    return render_template('gastos/form.html', action='Registrar', gasto=None, today=today)


# ──────────────────────────────────────────────
#  EDITAR GASTO (admin only)
# ──────────────────────────────────────────────
@gastos_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def edit(id):
    gasto = Gasto.query.get_or_404(id)

    if request.method == 'POST':
        concepto = request.form.get('concepto', '').strip()
        categoria = request.form.get('categoria', '').strip()
        monto = request.form.get('monto', type=int)
        moneda = request.form.get('moneda', '').strip()
        fecha_str = request.form.get('fecha', '').strip()
        observaciones = request.form.get('observaciones', '').strip()

        if not concepto or not categoria or not moneda or monto is None or monto <= 0:
            flash('Completa todos los campos obligatorios.', 'warning')
            return redirect(url_for('gastos.edit', id=id))

        try:
            gasto.fecha = date.fromisoformat(fecha_str) if fecha_str else date.today()
        except ValueError:
            flash('Fecha inválida. Usa el formato AAAA-MM-DD.', 'warning')
            return redirect(url_for('gastos.edit', id=id))

        gasto.concepto = concepto
        gasto.categoria = categoria
        gasto.monto = monto
        gasto.moneda = moneda
        gasto.observaciones = observaciones if observaciones else None

        db.session.commit()
        flash(f'Gasto actualizado: {concepto}', 'success')
        return redirect(url_for('gastos.index'))

    today = gasto.fecha.isoformat()
    return render_template('gastos/form.html', action='Editar', gasto=gasto, today=today)


# ──────────────────────────────────────────────
#  ELIMINAR GASTO (admin only)
# ──────────────────────────────────────────────
@gastos_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete(id):
    gasto = Gasto.query.get_or_404(id)
    db.session.delete(gasto)
    db.session.commit()
    flash(f'Gasto eliminado: {gasto.concepto}', 'info')
    return redirect(url_for('gastos.index'))
