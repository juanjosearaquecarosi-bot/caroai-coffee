from flask import Blueprint, render_template
from flask_login import login_required
from ..models import db, Pedido, PedidoItem, Mesa
from ..utils.decorators import role_required
from datetime import datetime, date

reports_bp = Blueprint('reports', __name__)

@reports_bp.route('/')
@login_required
@role_required('admin', 'employee')
def index():
    """Daily report — accessible by both admin and employee."""
    today = date.today()

    # Get all pedidos closed today
    today_start = datetime(today.year, today.month, today.day, 0, 0, 0)
    today_end = datetime(today.year, today.month, today.day, 23, 59, 59)

    pedidos_hoy = Pedido.query.filter(
        Pedido.fecha_hora >= today_start,
        Pedido.fecha_hora <= today_end,
        Pedido.estado == 'cerrado'
    ).order_by(Pedido.fecha_hora.asc()).all()

    # Totals
    total_vendido_cop = sum(item.subtotal_cop for pedido in pedidos_hoy for item in pedido.items)
    total_pedidos_hoy = len(pedidos_hoy)

    # Breakdown by currency received
    monedas_resumen = {}
    for pedido in pedidos_hoy:
        moneda = pedido.moneda_recibida
        if moneda not in monedas_resumen:
            monedas_resumen[moneda] = {
                'monto_total': 0,
                'cantidad_pedidos': 0,
            }
        monedas_resumen[moneda]['monto_total'] += pedido.monto_recibido
        monedas_resumen[moneda]['cantidad_pedidos'] += 1

    # Most sold products today
    productos_vendidos = {}
    for pedido in pedidos_hoy:
        for item in pedido.items:
            nombre = item.producto.nombre
            if nombre not in productos_vendidos:
                productos_vendidos[nombre] = 0
            productos_vendidos[nombre] += item.cantidad

    top_productos = sorted(productos_vendidos.items(), key=lambda x: x[1], reverse=True)[:10]

    # Active tables
    mesas_activas = Mesa.query.filter_by(estado='ocupada').count()
    mesas_libres = Mesa.query.filter_by(estado='libre').count()
    mesas_cerradas = Mesa.query.filter_by(estado='cerrada').count()

    return render_template(
        'reports/index.html',
        fecha=today,
        total_vendido_cop=total_vendido_cop,
        total_pedidos_hoy=total_pedidos_hoy,
        monedas_resumen=monedas_resumen,
        top_productos=top_productos,
        pedidos_hoy=pedidos_hoy,
        mesas_activas=mesas_activas,
        mesas_libres=mesas_libres,
        mesas_cerradas=mesas_cerradas,
    )


@reports_bp.route('/monthly')
@login_required
@role_required('admin')
def monthly():
    """Monthly report — admin only."""
    today = date.today()
    month_start = date(today.year, today.month, 1)

    # All closed pedidos this month
    pedidos_mes = Pedido.query.filter(
        Pedido.fecha_hora >= datetime(month_start.year, month_start.month, 1, 0, 0, 0),
        Pedido.fecha_hora <= datetime(today.year, today.month, today.day, 23, 59, 59),
        Pedido.estado == 'cerrado'
    ).order_by(Pedido.fecha_hora.asc()).all()

    total_vendido_cop = sum(item.subtotal_cop for pedido in pedidos_mes for item in pedido.items)
    total_pedidos_mes = len(pedidos_mes)

    # By currency
    monedas_resumen = {}
    for pedido in pedidos_mes:
        moneda = pedido.moneda_recibida
        if moneda not in monedas_resumen:
            monedas_resumen[moneda] = {
                'monto_total': 0,
                'cantidad_pedidos': 0,
            }
        monedas_resumen[moneda]['monto_total'] += pedido.monto_recibido
        monedas_resumen[moneda]['cantidad_pedidos'] += 1

    # By day
    ventas_por_dia = {}
    for pedido in pedidos_mes:
        dia = pedido.fecha_hora.strftime('%d/%m')
        if dia not in ventas_por_dia:
            ventas_por_dia[dia] = 0
        ventas_por_dia[dia] += sum(item.subtotal_cop for item in pedido.items)

    # Top products
    productos_vendidos = {}
    for pedido in pedidos_mes:
        for item in pedido.items:
            nombre = item.producto.nombre
            if nombre not in productos_vendidos:
                productos_vendidos[nombre] = 0
            productos_vendidos[nombre] += item.cantidad
    top_productos = sorted(productos_vendidos.items(), key=lambda x: x[1], reverse=True)[:10]

    return render_template(
        'reports/monthly.html',
        mes=today.strftime('%B %Y'),
        total_vendido_cop=total_vendido_cop,
        total_pedidos_mes=total_pedidos_mes,
        monedas_resumen=monedas_resumen,
        top_productos=top_productos,
        ventas_por_dia=ventas_por_dia,
    )
