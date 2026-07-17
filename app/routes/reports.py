from flask import Blueprint, render_template, request
from flask_login import login_required
from ..models import db, Pedido, Ubicacion, Gasto, TasaCambio
from ..utils.decorators import role_required
from datetime import datetime, date

reports_bp = Blueprint('reports', __name__)


@reports_bp.route('/')
@login_required
@role_required('admin', 'employee')
def index():
    """Daily report — accessible by both admin and employee."""
    today = date.today()

    today_start = datetime(today.year, today.month, today.day, 0, 0, 0)
    today_end = datetime(today.year, today.month, today.day, 23, 59, 59)

    pedidos_hoy = Pedido.query.filter(
        Pedido.pagado_en >= today_start,
        Pedido.pagado_en <= today_end,
        Pedido.estado == 'pagado',
    ).order_by(Pedido.pagado_en.asc()).all()

    total_vendido_cop = sum(item.subtotal_cop for pedido in pedidos_hoy for item in pedido.items)
    total_pedidos_hoy = len(pedidos_hoy)

    # Desglose por moneda de pago
    monedas_resumen = {}
    for pedido in pedidos_hoy:
        moneda = pedido.moneda_pago or '—'
        if moneda not in monedas_resumen:
            monedas_resumen[moneda] = {
                'monto_total': 0,
                'cantidad_pedidos': 0,
            }
        monedas_resumen[moneda]['monto_total'] += pedido.total
        monedas_resumen[moneda]['cantidad_pedidos'] += 1

    # Productos más vendidos
    productos_vendidos = {}
    for pedido in pedidos_hoy:
        for item in pedido.items:
            nombre = item.producto.nombre
            productos_vendidos[nombre] = productos_vendidos.get(nombre, 0) + item.cantidad
    top_productos = sorted(productos_vendidos.items(), key=lambda x: x[1], reverse=True)[:10]

    # Estado de ubicaciones
    ubicaciones_libres = Ubicacion.query.filter_by(estado='libre').count()
    ubicaciones_ocupadas = Ubicacion.query.filter_by(estado='ocupada').count()

    return render_template(
        'reports/index.html',
        fecha=today,
        total_vendido_cop=total_vendido_cop,
        total_pedidos_hoy=total_pedidos_hoy,
        monedas_resumen=monedas_resumen,
        top_productos=top_productos,
        pedidos_hoy=pedidos_hoy,
        ubicaciones_libres=ubicaciones_libres,
        ubicaciones_ocupadas=ubicaciones_ocupadas,
    )


@reports_bp.route('/monthly')
@login_required
@role_required('admin')
def monthly():
    """Monthly report — admin only.
    Incluye selector de mes/año, gastos, y balance unificado opcional via TasaCambio.
    """
    today = date.today()
    selected_mes = request.args.get('mes', type=int, default=today.month)
    selected_anio = request.args.get('anio', type=int, default=today.year)

    if selected_mes < 1 or selected_mes > 12:
        selected_mes = today.month
    if selected_anio < 2000 or selected_anio > 2100:
        selected_anio = today.year

    month_start = date(selected_anio, selected_mes, 1)
    if selected_mes == 12:
        month_end = date(selected_anio + 1, 1, 1)
    else:
        month_end = date(selected_anio, selected_mes + 1, 1)

    month_start_dt = datetime(month_start.year, month_start.month, month_start.day, 0, 0, 0)
    month_end_dt = datetime(month_end.year, month_end.month, month_end.day, 0, 0, 0)

    # ── Pedidos pagados del mes ──
    pedidos_mes = Pedido.query.filter(
        Pedido.pagado_en >= month_start_dt,
        Pedido.pagado_en < month_end_dt,
        Pedido.estado == 'pagado',
    ).order_by(Pedido.pagado_en.asc()).all()

    total_vendido_cop = sum(item.subtotal_cop for pedido in pedidos_mes for item in pedido.items)
    total_pedidos_mes = len(pedidos_mes)

    # ── Ingresos por moneda ──
    monedas_resumen = {}
    for pedido in pedidos_mes:
        moneda = pedido.moneda_pago or '—'
        if moneda not in monedas_resumen:
            monedas_resumen[moneda] = {
                'monto_total': 0,
                'cantidad_pedidos': 0,
            }
        monedas_resumen[moneda]['monto_total'] += pedido.total
        monedas_resumen[moneda]['cantidad_pedidos'] += 1

    # ── Ventas por día ──
    ventas_por_dia = {}
    for pedido in pedidos_mes:
        dia = pedido.pagado_en.strftime('%d/%m') if pedido.pagado_en else pedido.fecha_hora.strftime('%d/%m')
        ventas_por_dia[dia] = ventas_por_dia.get(dia, 0) + sum(
            item.subtotal_cop for item in pedido.items
        )

    # ── Top productos ──
    productos_vendidos = {}
    for pedido in pedidos_mes:
        for item in pedido.items:
            nombre = item.producto.nombre
            productos_vendidos[nombre] = productos_vendidos.get(nombre, 0) + item.cantidad
    top_productos = sorted(productos_vendidos.items(), key=lambda x: x[1], reverse=True)[:10]

    # ── Tazas de café vendidas ──
    palabras_cafe = {'café', 'cafe', 'capuchino', 'espresso', 'expreso', 'latte', 'moka', 'macchiato'}
    tazas_cafe = 0
    total_items_vendidos = 0
    for pedido in pedidos_mes:
        for item in pedido.items:
            nombre_lower = item.producto.nombre.lower()
            total_items_vendidos += item.cantidad
            if any(p in nombre_lower for p in palabras_cafe):
                tazas_cafe += item.cantidad

    # ── Gastos del mes ──
    gastos_mes = Gasto.query.filter(
        Gasto.fecha >= month_start,
        Gasto.fecha < month_end,
    ).order_by(Gasto.fecha.desc()).all()

    gastos_por_categoria = {}
    gastos_por_moneda = {}
    total_gastos_global = 0
    for gasto in gastos_mes:
        cat = gasto.categoria
        if cat not in gastos_por_categoria:
            gastos_por_categoria[cat] = {
                'monto': 0,
                'monedas': set(),
                'cantidad': 0,
            }
        gastos_por_categoria[cat]['monto'] += gasto.monto
        gastos_por_categoria[cat]['monedas'].add(gasto.moneda)
        gastos_por_categoria[cat]['cantidad'] += 1

        mon = gasto.moneda
        if mon not in gastos_por_moneda:
            gastos_por_moneda[mon] = 0
        gastos_por_moneda[mon] += gasto.monto
        total_gastos_global += gasto.monto

    # ── Balance simple (COP) ──
    gastos_cop = gastos_por_moneda.get('COP', 0)
    balance_cop = total_vendido_cop - gastos_cop

    # ── Balance unificado (opcional, requiere TasaCambio) ──
    tasas_relevantes = {}
    # Buscar tasas COP → USD y COP → VES vigentes
    for par in [('COP', 'USD'), ('COP', 'VES'), ('USD', 'COP'), ('VES', 'COP')]:
        tasa = TasaCambio.query.filter_by(
            moneda_origen=par[0],
            moneda_destino=par[1],
        ).order_by(TasaCambio.vigente_desde.desc()).first()
        if tasa:
            tasas_relevantes[f'{par[0]}→{par[1]}'] = tasa

    balance_unificado = None
    tasa_usada = None
    if 'COP→USD' in tasas_relevantes:
        tasa_usd = tasas_relevantes['COP→USD'].tasa
        # Convertir todo a USD (ingresos COP + gastos COP + gastos USD ya están en USD)
        # Solo podemos convertir COP a USD con precisión
        ingresos_usd = round(total_vendido_cop / tasa_usd, 2)
        gastos_usd = round(gastos_cop / tasa_usd, 2)
        gastos_usd_directos = gastos_por_moneda.get('USD', 0)
        total_gastos_usd = gastos_usd + gastos_usd_directos
        balance_usd = round(ingresos_usd - total_gastos_usd, 2)
        balance_unificado = {
            'moneda': 'USD',
            'ingresos': ingresos_usd,
            'gastos': total_gastos_usd,
            'balance': balance_usd,
            'tasa_usada': f'1 COP = {1/tasa_usd:.6f} USD' if tasa_usd > 0 else 'N/A',
            'tasa_origen': tasas_relevantes['COP→USD'],
        }
        tasa_usada = 'COP→USD'

    return render_template(
        'reports/monthly.html',
        selected_mes=selected_mes,
        selected_anio=selected_anio,
        mes_nombre=month_start.strftime('%B %Y'),
        total_vendido_cop=total_vendido_cop,
        total_pedidos_mes=total_pedidos_mes,
        monedas_resumen=monedas_resumen,
        top_productos=top_productos,
        ventas_por_dia=ventas_por_dia,
        tazas_cafe=tazas_cafe,
        total_items_vendidos=total_items_vendidos,
        gastos_mes=gastos_mes,
        gastos_por_categoria=gastos_por_categoria,
        gastos_por_moneda=gastos_por_moneda,
        total_gastos_global=total_gastos_global,
        gastos_cop=gastos_cop,
        balance_cop=balance_cop,
        balance_unificado=balance_unificado,
        tasas_relevantes=tasas_relevantes,
    )
