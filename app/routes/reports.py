from collections import defaultdict
from flask import Blueprint, render_template, request
from flask_login import login_required
from ..models import db, Pedido, Mesa, Gasto, TasaCambio
from ..utils.decorators import role_required
from ..utils.currency import obtener_tasas_cop, get_tasa_activa
from datetime import datetime, date

reports_bp = Blueprint('reports', __name__)


def _obtener_tasa_ves_cop():
    """Get VES→COP rate, trying typed (venta/compra) first, then direct, then inverse."""
    for tipo in ('ves_venta', 'ves_compra', None):
        t = get_tasa_activa('VES', 'COP', tipo=tipo) if tipo else get_tasa_activa('VES', 'COP')
        if t:
            return t.tasa
    t = get_tasa_activa('COP', 'VES')
    if t and t.tasa > 0:
        return round(1 / t.tasa, 2)
    return None


@reports_bp.route('/')
@login_required
@role_required('admin', 'empleado')
def index():
    """Daily report — accessible by both admin and empleado."""
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

    # ── Pedidos pendientes (deuda) ──
    pedidos_pendientes = Pedido.query.filter(
        Pedido.estado == 'pendiente',
    ).all()
    total_pendientes_hoy = len(pedidos_pendientes)
    total_deuda_pendiente = sum(p.total for p in pedidos_pendientes)

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

    # Estado de mesas
    mesas_libres = Mesa.query.filter_by(estado='libre').count()
    mesas_ocupadas = Mesa.query.filter_by(estado='ocupada').count()

    return render_template(
        'reports/index.html',
        fecha=today,
        total_vendido_cop=total_vendido_cop,
        total_pedidos_hoy=total_pedidos_hoy,
        total_pendientes_hoy=total_pendientes_hoy,
        total_deuda_pendiente=total_deuda_pendiente,
        monedas_resumen=monedas_resumen,
        top_productos=top_productos,
        pedidos_hoy=pedidos_hoy,
        pedidos_pendientes=pedidos_pendientes,
        mesas_libres=mesas_libres,
        mesas_ocupadas=mesas_ocupadas,
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

    # ── Ingresos por moneda (montos reales en cada moneda) ──
    monedas_resumen = {}
    for pedido in pedidos_mes:
        moneda = pedido.moneda_pago or '—'
        if moneda not in monedas_resumen:
            monedas_resumen[moneda] = {
                'monto_total': 0,
                'cantidad_pedidos': 0,
            }
        monedas_resumen[moneda]['monto_total'] += _monto_en_moneda(pedido)
        monedas_resumen[moneda]['cantidad_pedidos'] += 1

    # ── Ventas por día (montos reales por moneda) ──
    ventas_por_dia = {}
    for pedido in pedidos_mes:
        dia = pedido.pagado_en.strftime('%d/%m') if pedido.pagado_en else pedido.fecha_hora.strftime('%d/%m')
        ventas_por_dia[dia] = ventas_por_dia.get(dia, 0) + _monto_en_moneda(pedido)

    # ── Desglose diario: facturas individuales por día ──
    tasa_ves_cop = _obtener_tasa_ves_cop()

    facturas_por_dia = defaultdict(list)
    for pedido in pedidos_mes:
        dia = pedido.pagado_en.day if pedido.pagado_en else pedido.fecha_hora.day
        moneda = (pedido.moneda_pago or 'COP').upper()
        monto_real = _monto_en_moneda(pedido)
        cop_ref = round(monto_real * tasa_ves_cop, 2) if moneda == 'VES' and tasa_ves_cop else None
        facturas_por_dia[dia].append({
            'pedido_id': pedido.id,
            'mesa': pedido.mesa.nombre if pedido.mesa else '—',
            'hora': pedido.pagado_en.strftime('%H:%M') if pedido.pagado_en else '—',
            'moneda': moneda,
            'total': monto_real,
            'cop_ref': cop_ref,
            'line_items': [
                {
                    'producto': item.nota or (item.producto.nombre if item.producto else 'Cargo manual'),
                    'cantidad': item.cantidad,
                    'subtotal_cop': item.subtotal_cop,
                }
                for item in pedido.items
            ],
        })
    facturas_por_dia = dict(sorted(facturas_por_dia.items()))

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

    # ── Balance unificado (opcional, usando tasa centralizada) ──
    _, _, _, _, tasa_tachira = obtener_tasas_cop()

    balance_unificado = None
    tasa_usada = None

    # Usar Tasa Táchira si existe, sino directa USD→COP
    tasa_usd_obj = get_tasa_activa('USD', 'COP', tipo='tachira_usd') if not tasa_tachira else None
    tasa_usd_para_reporte = tasa_tachira
    if not tasa_usd_para_reporte:
        tasa_usd_obj = get_tasa_activa('USD', 'COP')
        if tasa_usd_obj:
            tasa_usd_para_reporte = tasa_usd_obj.tasa

    if tasa_usd_para_reporte:
        tasa_usd = tasa_usd_para_reporte
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
            'tasa_usada': f'1 USD = {tasa_usd:,.2f} COP' if tasa_usd > 0 else 'N/A',
            'tasa_origen': None,
        }
        tasa_usada = 'USD→COP'

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
        facturas_por_dia=facturas_por_dia,
        tasa_ves_cop=tasa_ves_cop,
    )


# ──────────────────────────────────────────────
#  COMPARACIÓN ENTRE MESES (Fase 4)
#  Usa SOLO datos guardados en el momento del cobro:
#  Pedido.total, moneda_pago, tasa_aplicada y total_pagado_moneda.
#  No recalcula ventas pasadas con tasas de cambio nuevas.
#  Solo entran pedidos con estado 'pagado' (anulados/pendientes quedan fuera).
# ──────────────────────────────────────────────

NOMBRES_MES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
               'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']


def _monto_en_moneda(pedido):
    """Monto cobrado en la moneda del pedido, tal como se guardó en el cobro.
    Prioriza total_pagado_moneda; si falta (datos viejos), deriva de total/tasa_aplicada.
    Para COP o datos sin info de moneda, retorna pedido.total (que ya está en COP)."""
    if pedido.total_pagado_moneda:
        return pedido.total_pagado_moneda
    if pedido.tasa_aplicada and pedido.tasa_aplicada > 0:
        return round(pedido.total / pedido.tasa_aplicada, 2)
    return float(pedido.total)


def _resumen_mes(mes, anio):
    """Agrega las métricas comparables de un mes (pedidos pagados + gastos)."""
    month_start = date(anio, mes, 1)
    if mes == 12:
        month_end = date(anio + 1, 1, 1)
    else:
        month_end = date(anio, mes + 1, 1)

    month_start_dt = datetime(month_start.year, month_start.month, month_start.day, 0, 0, 0)
    month_end_dt = datetime(month_end.year, month_end.month, month_end.day, 0, 0, 0)

    pedidos = Pedido.query.filter(
        Pedido.pagado_en >= month_start_dt,
        Pedido.pagado_en < month_end_dt,
        Pedido.estado == 'pagado',
    ).all()

    total_vendido_cop = sum(p.total for p in pedidos)
    monto_cop = sum(p.total for p in pedidos if p.moneda_pago == 'COP')
    monto_usd = 0.0
    monto_ves = 0.0
    tasas_usd = []
    tasas_ves = []

    for p in pedidos:
        if p.moneda_pago == 'USD':
            monto_usd += _monto_en_moneda(p)
            if p.tasa_aplicada:
                tasas_usd.append(p.tasa_aplicada)
        elif p.moneda_pago == 'VES':
            monto_ves += _monto_en_moneda(p)
            if p.tasa_aplicada:
                tasas_ves.append(p.tasa_aplicada)

    gastos = Gasto.query.filter(
        Gasto.fecha >= month_start,
        Gasto.fecha < month_end,
    ).all()
    gastos_por_moneda = {}
    for g in gastos:
        gastos_por_moneda[g.moneda] = gastos_por_moneda.get(g.moneda, 0) + g.monto

    return {
        'mes': mes,
        'anio': anio,
        'mes_nombre': NOMBRES_MES[mes - 1],
        'total_vendido_cop': total_vendido_cop,
        'monto_cop': monto_cop,
        'monto_usd': round(monto_usd, 2),
        'monto_ves': round(monto_ves, 2),
        'num_pedidos': len(pedidos),
        'tasa_usd': (sum(tasas_usd) / len(tasas_usd)) if tasas_usd else None,
        'tasa_ves': (sum(tasas_ves) / len(tasas_ves)) if tasas_ves else None,
        'gasto_total': sum(gastos_por_moneda.values()),
        'gastos_por_moneda': gastos_por_moneda,
    }


def _meses_con_datos():
    """Meses (anio, mes) con pedidos pagados o gastos, ordenados desc."""
    pares = set()
    for (fecha_pagado,) in Pedido.query.filter_by(estado='pagado').with_entities(Pedido.pagado_en).all():
        if fecha_pagado:
            pares.add((fecha_pagado.year, fecha_pagado.month))
    for (fecha_gasto,) in Gasto.query.with_entities(Gasto.fecha).all():
        if fecha_gasto:
            pares.add((fecha_gasto.year, fecha_gasto.month))
    return sorted(pares, reverse=True)


def _construir_filas(ra, rb):
    """Filas de la tabla comparativa: etiqueta, valor A, valor B, tipo."""
    return [
        {'etiqueta': 'Total vendido (COP)', 'a': ra['total_vendido_cop'], 'b': rb['total_vendido_cop'], 'tipo': 'monto', 'simbolo': '$', 'decimales': 0},
        {'etiqueta': 'Monto pagado en COP', 'a': ra['monto_cop'], 'b': rb['monto_cop'], 'tipo': 'monto', 'simbolo': '$', 'decimales': 0},
        {'etiqueta': 'Monto pagado en USD', 'a': ra['monto_usd'], 'b': rb['monto_usd'], 'tipo': 'monto', 'simbolo': 'US$', 'decimales': 2},
        {'etiqueta': 'Monto pagado en VES', 'a': ra['monto_ves'], 'b': rb['monto_ves'], 'tipo': 'monto', 'simbolo': 'Bs', 'decimales': 2},
        {'etiqueta': 'Pedidos pagados', 'a': ra['num_pedidos'], 'b': rb['num_pedidos'], 'tipo': 'contador'},
        {'etiqueta': 'Tasa USD usada (prom.)', 'a': ra['tasa_usd'], 'b': rb['tasa_usd'], 'tipo': 'tasa'},
        {'etiqueta': 'Tasa VES usada (prom.)', 'a': ra['tasa_ves'], 'b': rb['tasa_ves'], 'tipo': 'tasa'},
        {'etiqueta': 'Gasto total', 'a': ra['gasto_total'], 'b': rb['gasto_total'], 'tipo': 'monto', 'simbolo': '$', 'decimales': 0},
    ]


@reports_bp.route('/compare')
@login_required
@role_required('admin')
def compare():
    """Compara dos meses usando datos guardados en el cobro. Admin only."""
    today = date.today()
    mes_a = request.args.get('mes_a', type=int, default=today.month)
    anio_a = request.args.get('anio_a', type=int, default=today.year)
    mes_b = request.args.get('mes_b', type=int,
                             default=(12 if today.month == 1 else today.month - 1))
    anio_b = request.args.get('anio_b', type=int,
                              default=(today.year - 1 if today.month == 1 else today.year))

    if mes_a < 1 or mes_a > 12:
        mes_a = today.month
    if mes_b < 1 or mes_b > 12:
        mes_b = today.month
    if anio_a < 2000 or anio_a > 2100:
        anio_a = today.year
    if anio_b < 2000 or anio_b > 2100:
        anio_b = today.year

    resumen_a = _resumen_mes(mes_a, anio_a)
    resumen_b = _resumen_mes(mes_b, anio_b)

    anios = sorted({a for a, _ in _meses_con_datos()} | {anio_a, anio_b, today.year},
                   reverse=True)

    return render_template(
        'reports/compare.html',
        resumen_a=resumen_a,
        resumen_b=resumen_b,
        filas=_construir_filas(resumen_a, resumen_b),
        mes_a=mes_a, anio_a=anio_a,
        mes_b=mes_b, anio_b=anio_b,
        anios=anios,
    )


# ──────────────────────────────────────────────
#  RESUMEN ANUAL
#  Tabla comparativa mes a mes dentro de un año:
#  Tazas, Kilos, Bs, COP, US$, Análisis mes.
# ──────────────────────────────────────────────
MESES_CORTOS = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
                'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

PALABRAS_CAFE = {'café', 'cafe', 'capuchino', 'espresso', 'expreso',
                 'latte', 'moka', 'macchiato', 'cortado', 'macchiato'}

# Kilos: productos con 'kilo' en el nombre.  Multiplicador por nombre.
# Orden importa: patrones más específicos primero para evitar match parcial.
KILO_FACTORS = [
    ('½ kilo', 0.5), ('1/2 kilo', 0.5), ('medio kilo', 0.5),
    ('¼ kilo', 0.25), ('1/4 kilo', 0.25), ('cuarto kilo', 0.25),
    ('kilo', 1.0),  # genérico al final
]


@reports_bp.route('/annual')
@login_required
@role_required('admin')
def annual_summary():
    """Resumen anual: tabla de 12 meses con tazas, kilos, Bs, COP, US$."""
    from ..models import AnalisisMensual

    today = date.today()
    selected_anio = request.args.get('anio', type=int, default=today.year)
    if selected_anio < 2000 or selected_anio > 2100:
        selected_anio = today.year

    year_start = date(selected_anio, 1, 1)
    year_end = date(selected_anio + 1, 1, 1)
    year_start_dt = datetime(selected_anio, 1, 1, 0, 0, 0)
    year_end_dt = datetime(selected_anio + 1, 1, 1, 0, 0, 0)

    pedidos_anio = Pedido.query.filter(
        Pedido.pagado_en >= year_start_dt,
        Pedido.pagado_en < year_end_dt,
        Pedido.estado == 'pagado',
    ).all()

    # ── VES→COP rate for reference display ──
    tasa_ves_cop = _obtener_tasa_ves_cop()

    # ── Cálculo por mes ──
    filas = []
    for mes_num in range(1, 13):
        tazas = 0
        kilos = 0.0
        bs = 0
        cop = 0
        usd = 0.0

        for pedido in pedidos_anio:
            if not pedido.pagado_en or pedido.pagado_en.month != mes_num:
                continue

            # Moneda (vacío o None se trata como COP por defecto)
            moneda = (pedido.moneda_pago or 'COP').upper()
            monto = _monto_en_moneda(pedido)
            if moneda == 'VES':
                bs += monto
            elif moneda == 'USD':
                usd += monto
            else:
                cop += pedido.total

            for item in pedido.items:
                if not item.producto:
                    continue
                nombre_lower = item.producto.nombre.lower()

                # Tazas de café
                if any(p in nombre_lower for p in PALABRAS_CAFE):
                    tazas += item.cantidad

                # Kilos de café en grano
                for keyword, factor in KILO_FACTORS:
                    if keyword in nombre_lower:
                        kilos += item.cantidad * factor
                        break

        filas.append({
            'mes': mes_num,
            'mes_nombre': MESES_CORTOS[mes_num - 1],
            'tazas': tazas,
            'kilos': round(kilos, 3) if kilos else 0,
            'bs': bs,
            'bs_cop_ref': round(bs * tasa_ves_cop, 2) if tasa_ves_cop else None,
            'cop': cop,
            'usd': round(usd, 2) if usd else 0,
        })

    # ── Fila de totales ──
    total_tazas = sum(f['tazas'] for f in filas)
    total_kilos = round(sum(f['kilos'] for f in filas), 3)
    total_bs = sum(f['bs'] for f in filas)
    total_bs_cop_ref = round(total_bs * tasa_ves_cop, 2) if tasa_ves_cop else None
    total_cop = sum(f['cop'] for f in filas)
    total_usd = round(sum(f['usd'] for f in filas), 2)

    # ── Análisis mensual (notas persistentes) ──
    analisis_map = {}
    notas = AnalisisMensual.query.filter_by(anio=selected_anio).all()
    for nota in notas:
        analisis_map[nota.mes] = nota.texto or ''

    # Años disponibles (con datos o actuales)
    anios_con_datos = set()
    for (fecha,) in Pedido.query.filter_by(estado='pagado').with_entities(Pedido.pagado_en).all():
        if fecha is not None:
            anios_con_datos.add(fecha.year)
    anios = sorted(anios_con_datos | {today.year}, reverse=True)

    return render_template(
        'reports/annual.html',
        selected_anio=selected_anio,
        filas=filas,
        total_tazas=total_tazas,
        total_kilos=total_kilos,
        total_bs=total_bs,
        total_bs_cop_ref=total_bs_cop_ref,
        total_cop=total_cop,
        total_usd=total_usd,
        analisis_map=analisis_map,
        anios=anios,
        tasa_ves_cop=tasa_ves_cop,
    )


@reports_bp.route('/annual/save-note', methods=['POST'])
@login_required
@role_required('admin')
def save_annual_note():
    """Guarda o actualiza el análisis mensual (texto libre)."""
    from ..models import AnalisisMensual
    from flask import jsonify

    anio = request.form.get('anio', type=int)
    mes = request.form.get('mes', type=int)
    texto = request.form.get('texto', '').strip()

    if not anio or not mes or mes < 1 or mes > 12:
        return jsonify({'ok': False, 'error': 'Parámetros inválidos'}), 400

    nota = AnalisisMensual.query.filter_by(anio=anio, mes=mes).first()
    if nota:
        nota.texto = texto
    else:
        nota = AnalisisMensual(anio=anio, mes=mes, texto=texto)
        db.session.add(nota)

    db.session.commit()
    return jsonify({'ok': True})
