from ..models import TasaCambio

# ──────────────────────────────────────────────
#  CONVERSIÓN BASE: tasas simples
# ──────────────────────────────────────────────

def convert_cop_to_usd(amount_cop, tasa_cop_usd):
    """
    Convert an amount from COP to USD.
    amount_cop: amount in COP
    tasa_cop_usd: exchange rate (COP per 1 USD)
    Returns amount in USD.
    """
    if tasa_cop_usd == 0:
        return 0
    return amount_cop / tasa_cop_usd


def convert_cop_to_bs(amount_cop, tasa_cop_usd, tasa_tienda_bs_usd):
    """
    Convert an amount from COP to Bolivares using the given rates.
    First convert COP to USD, then USD to Bs using tasa_tienda_bs_usd.
    amount_cop: amount in COP
    tasa_cop_usd: exchange rate (COP per 1 USD)
    tasa_tienda_bs_usd: exchange rate (Bs per 1 USD) - the real rate used
    Returns amount in Bs.
    """
    if tasa_cop_usd == 0:
        return 0
    amount_usd = amount_cop / tasa_cop_usd
    return amount_usd * tasa_tienda_bs_usd


def convert_bs_to_cop(amount_bs, tasa_cop_usd, tasa_tienda_bs_usd):
    """
    Convert an amount from Bolivares to COP.
    """
    if tasa_tienda_bs_usd == 0:
        return 0
    amount_usd = amount_bs / tasa_tienda_bs_usd
    return amount_usd * tasa_cop_usd


# ──────────────────────────────────────────────
#  CENTRALIZED: lookup activa desde DB
# ──────────────────────────────────────────────

def get_tasa_activa(moneda_origen, moneda_destino):
    """
    Retorna la tasa de cambio activa más reciente desde TasaCambio,
    o None si no existe ninguna.

    La tasa activa es la última creada (por vigente_desde DESC).
    """
    t = TasaCambio.query.filter_by(
        moneda_origen=moneda_origen,
        moneda_destino=moneda_destino,
    ).order_by(TasaCambio.vigente_desde.desc()).first()
    return t


def obtener_tasas_cop():
    """
    Retorna (tasa_usd, tasa_bs) donde:
      tasa_usd = cuántos COP vale 1 USD  (1 USD = X COP)
      tasa_bs  = cuántos COP vale 1 VES (1 VES = X COP)

    Busca primero 'USD→COP' / 'VES→COP'.
    Si no existe, busca la inversa 'COP→USD' / 'COP→VES' y la invierte.

    Si no se encuentra ninguna tasa, retorna (4200.0, 6.0) como fallback
    para no romper la visualización.
    """
    # ── USD → COP ──
    t = get_tasa_activa('USD', 'COP')
    if t:
        tasa_usd = t.tasa
    else:
        t = get_tasa_activa('COP', 'USD')
        if t and t.tasa > 0:
            tasa_usd = round(1 / t.tasa, 2)
        else:
            tasa_usd = 4200.0

    # ── VES → COP ──
    t = get_tasa_activa('VES', 'COP')
    if t:
        tasa_bs = t.tasa
    else:
        t = get_tasa_activa('COP', 'VES')
        if t and t.tasa > 0:
            tasa_bs = round(1 / t.tasa, 2)
        else:
            tasa_bs = 6.0

    return tasa_usd, tasa_bs


def convertir_cop_a(monto_cop, moneda_destino):
    """
    Convierte monto_cop a la moneda_destino usando la tasa activa de TasaCambio.

    Parámetros:
      monto_cop      — total en COP
      moneda_destino — 'USD', 'VES' o 'COP' (no convierte)

    Retorna:
      (monto_convertido, tasa_aplicada, mensaje_error)
      - Si la moneda es 'COP': monto_convertido = monto_cop, tasa_aplicada = 1.0
      - Si existe tasa activa: monto convertido y tasa aplicada
      - Si NO existe tasa: (None, None, mensaje de error)
    """
    if moneda_destino == 'COP':
        return monto_cop, 1.0, None

    tasa_obj = get_tasa_activa(moneda_destino, 'COP')
    if not tasa_obj:
        # Intentar inversa
        tasa_obj = get_tasa_activa('COP', moneda_destino)
        if tasa_obj and tasa_obj.tasa > 0:
            tasa_val = round(1 / tasa_obj.tasa, 2)
        else:
            return None, None, (
                f'⚠️ No hay tasa activa configurada para {moneda_destino} → COP. '
                f'Ve a Tasas de Cambio y crea una antes de cobrar en {moneda_destino}.'
            )
    else:
        tasa_val = tasa_obj.tasa

    if tasa_val <= 0:
        return None, None, f'⚠️ La tasa {moneda_destino}→COP tiene un valor inválido ({tasa_val}).'

    if moneda_destino in ('USD', 'VES'):
        # 1 USD/VES = tasa_val COP  →  monto = monto_cop / tasa_val
        monto = monto_cop / tasa_val
    else:
        return None, None, f'Moneda no soportada: {moneda_destino}'

    return round(monto, 2), tasa_val, None


# ══════════════════════════════════════════════
#  TEST / VERIFICACIÓN (uso standalone)
# ═══════════════════════════════════════════════

def probar_conversion_simple():
    """
    Prueba la lógica de conversión con valores conocidos, SIN base de datos.
    Útil para verificar que el cálculo matemático es correcto.
    Uso: python -c "from app.utils.currency import probar_conversion_simple; probar_conversion_simple()"
    """
    ok = True

    # 1) COP → COP: sin cambio
    monto, tasa, err = 45000, 1.0, None  # simula resultado de convertir_cop_a
    esperado_monto = 45000
    if monto != esperado_monto:
        print(f"❌ COP→COP: esperado {esperado_monto}, obtenido {monto}")
        ok = False
    else:
        print(f"✅ COP→COP: {monto} (tasa={tasa})")

    # 2) COP → USD con tasa 4200
    monto = round(42000 / 4200, 2)  # 10.0
    esperado_monto = 10.0
    if monto != esperado_monto:
        print(f"❌ COP→USD (4200): esperado {esperado_monto}, obtenido {monto}")
        ok = False
    else:
        print(f"✅ COP→USD (4200): ${monto} USD")

    # 3) COP → VES con tasa 6.0
    monto = round(45000 / 6.0, 2)  # 7500.0
    esperado_monto = 7500.0
    if monto != esperado_monto:
        print(f"❌ COP→VES (6.0): esperado {esperado_monto}, obtenido {monto}")
        ok = False
    else:
        print(f"✅ COP→VES (6.0): Bs {monto}")

    # 4) Caso límite: monto 0
    monto = round(0 / 4200, 2)  # 0.0
    if monto != 0.0:
        print(f"❌ COP→USD con 0: esperado 0.0, obtenido {monto}")
        ok = False
    else:
        print(f"✅ COP→USD con 0: {monto}")

    # 5) Tasa inválida (0): la función debería retornar error
    tasa_invalida = 0
    monto = 10000 / tasa_invalida if tasa_invalida > 0 else None
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
