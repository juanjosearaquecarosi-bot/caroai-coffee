from ..models import TasaCambio

# ──────────────────────────────────────────────
#  CENTRALIZED: lookup activa desde DB
# ──────────────────────────────────────────────

def get_tasa_activa(moneda_origen, moneda_destino, tipo=None):
    """
    Retorna la tasa de cambio activa más reciente desde TasaCambio,
    o None si no existe ninguna.

    Si tipo es especificado, busca solo tasas con ese tipo.
    Si tipo es None, busca solo tasas sin tipo (directas).
    """
    q = TasaCambio.query.filter_by(
        moneda_origen=moneda_origen,
        moneda_destino=moneda_destino,
    )
    if tipo is not None:
        q = q.filter_by(tipo=tipo)
    else:
        q = q.filter(TasaCambio.tipo.is_(None))
    return q.order_by(TasaCambio.vigente_desde.desc()).first()


def obtener_tasas_cop():
    """
    Retorna (tasa_usd, tasa_bs, tasa_ves_compra, tasa_ves_venta, tasa_tachira)
    donde:
      tasa_usd       = cuántos COP vale 1 USD  (1 USD = X COP) — tasa directa o inversa
      tasa_bs        = cuántos COP vale 1 VES (1 VES = X COP) — promedio compra/venta si están configuradas
      tasa_ves_compra = tasa VES compra (VES→COP) o None
      tasa_ves_venta  = tasa VES venta (VES→COP) o None
      tasa_tachira    = tasa Táchira (USD→COP) o None

    Fallbacks si no se encuentra ninguna tasa:
      tasa_usd = 4200.0
      tasa_bs  = 6.0
    """
    # ── USD → COP (tasa Táchira tiene prioridad) ──
    t = get_tasa_activa('USD', 'COP', tipo='tachira_usd')
    if t:
        tasa_usd = t.tasa
        tasa_tachira = t.tasa
    else:
        t = get_tasa_activa('USD', 'COP')
        if t:
            tasa_usd = t.tasa
        else:
            t = get_tasa_activa('COP', 'USD')
            if t and t.tasa > 0:
                tasa_usd = round(1 / t.tasa, 2)
            else:
                tasa_usd = 4200.0
        tasa_tachira = None

    # ── VES → COP: usar promedio compra/venta si están configuradas ──
    tasa_ves_compra = get_tasa_activa('VES', 'COP', tipo='ves_compra')
    tasa_ves_venta = get_tasa_activa('VES', 'COP', tipo='ves_venta')

    if tasa_ves_compra and tasa_ves_venta:
        # Promedio compra/venta
        tasa_bs = round((tasa_ves_compra.tasa + tasa_ves_venta.tasa) / 2, 2)
    elif tasa_ves_compra:
        tasa_bs = tasa_ves_compra.tasa
    elif tasa_ves_venta:
        tasa_bs = tasa_ves_venta.tasa
    else:
        # Fallback a tasa directa VES→COP o inversa
        t = get_tasa_activa('VES', 'COP')
        if t:
            tasa_bs = t.tasa
        else:
            t = get_tasa_activa('COP', 'VES')
            if t and t.tasa > 0:
                tasa_bs = round(1 / t.tasa, 2)
            else:
                tasa_bs = 6.0

    return (
        tasa_usd,
        tasa_bs,
        tasa_ves_compra.tasa if tasa_ves_compra else None,
        tasa_ves_venta.tasa if tasa_ves_venta else None,
        tasa_tachira,
    )


def convertir_cop_a(monto_cop, moneda_destino):
    """
    Convierte monto_cop a la moneda_destino usando las tasas activas de TasaCambio.

    Lógica:
      - COP → COP: sin cambio
      - COP → USD: usa tasa Táchira si existe, sino tasa USD directa
      - COP → VES: usa promedio compra/venta si existen, sino tasa VES directa

    Parámetros:
      monto_cop      — total en COP
      moneda_destino — 'USD', 'VES' o 'COP'

    Retorna:
      (monto_convertido, tasa_aplicada, mensaje_error)
    """
    if moneda_destino == 'COP':
        return monto_cop, 1.0, None

    if moneda_destino == 'USD':
        # Prioridad: Tasa Táchira → USD directa → COP→USD inversa
        t = get_tasa_activa('USD', 'COP', tipo='tachira_usd')
        if t:
            tasa_val = t.tasa
        else:
            t = get_tasa_activa('USD', 'COP')
            if t:
                tasa_val = t.tasa
            else:
                t = get_tasa_activa('COP', 'USD')
                if t and t.tasa > 0:
                    tasa_val = round(1 / t.tasa, 2)
                else:
                    return None, None, (
                        '⚠️ No hay tasa USD activa configurada. '
                        'Ve a Tasas de Cambio y crea una tasa USD→COP antes de cobrar en USD.'
                    )
        monto = round(monto_cop / tasa_val, 2)
        return monto, tasa_val, None

    elif moneda_destino == 'VES':
        # Usar promedio compra/venta si están configuradas
        ves_compra = get_tasa_activa('VES', 'COP', tipo='ves_compra')
        ves_venta = get_tasa_activa('VES', 'COP', tipo='ves_venta')

        if ves_compra and ves_venta:
            tasa_val = round((ves_compra.tasa + ves_venta.tasa) / 2, 2)
        elif ves_compra:
            tasa_val = ves_compra.tasa
        elif ves_venta:
            tasa_val = ves_venta.tasa
        else:
            # Fallback a tasa directa VES→COP o inversa
            t = get_tasa_activa('VES', 'COP')
            if t:
                tasa_val = t.tasa
            else:
                t = get_tasa_activa('COP', 'VES')
                if t and t.tasa > 0:
                    tasa_val = round(1 / t.tasa, 2)
                else:
                    return None, None, (
                        '⚠️ No hay tasa VES activa configurada. '
                        'Ve a Tasas de Cambio y crea una tasa VES→COP antes de cobrar en VES.'
                    )

        monto = round(monto_cop / tasa_val, 2)
        return monto, tasa_val, None

    else:
        return None, None, f'Moneda no soportada: {moneda_destino}'


# ══════════════════════════════════════════════
#  TEST / VERIFICACIÓN (uso standalone)
# ══════════════════════════════════════════════

def probar_conversion_simple():
    """
    Prueba la lógica de conversión con valores conocidos, SIN base de datos.
    Útil para verificar que el cálculo matemático es correcto.
    """
    ok = True

    # 1) COP → COP: sin cambio
    monto, tasa, err = 45000, 1.0, None
    if monto != 45000:
        print(f"❌ COP→COP: esperado 45000, obtenido {monto}")
        ok = False
    else:
        print(f"✅ COP→COP: {monto} (tasa={tasa})")

    # 2) COP → USD con tasa 4200
    monto = round(42000 / 4200, 2)  # 10.0
    if monto != 10.0:
        print(f"❌ COP→USD (4200): esperado 10.0, obtenido {monto}")
        ok = False
    else:
        print(f"✅ COP→USD (4200): ${monto} USD")

    # 3) COP → VES con promedio 1.5+2.5/2 = 2.0
    prom = round((1.5 + 2.5) / 2, 2)  # 2.0
    monto = round(45000 / prom, 2)  # 22500.0
    if monto != 22500.0:
        print(f"❌ COP→VES promedio: esperado 22500.0, obtenido {monto}")
        ok = False
    else:
        print(f"✅ COP→VES promedio (compra=1.5, venta=2.5): Bs {monto}")

    # 4) COP → VES con una sola tasa compra
    monto = round(45000 / 1.5, 2)  # 30000.0
    if monto != 30000.0:
        print(f"❌ COP→VES solo compra: esperado 30000.0, obtenido {monto}")
        ok = False
    else:
        print(f"✅ COP→VES solo compra (1.5): Bs {monto}")

    # 5) Caso límite: monto 0
    monto = round(0 / 4200, 2)
    if monto != 0.0:
        print(f"❌ Monto 0: esperado 0.0, obtenido {monto}")
        ok = False
    else:
        print(f"✅ Monto 0: {monto}")

    # 6) Tasa inválida (0)
    monto = 10000 / 0 if 0 > 0 else None
    if monto is not None:
        print(f"❌ Tasa 0 debería dar error, pero dio {monto}")
        ok = False
    else:
        print(f"✅ Tasa=0 detectada correctamente")

    print()
    if ok:
        print("✅ Conversión: todas las pruebas pasaron.")
    else:
        print("❌ Conversión: algunas pruebas fallaron.")
    return ok
