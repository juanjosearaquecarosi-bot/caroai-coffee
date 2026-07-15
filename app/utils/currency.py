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

# Example usage:
# tasa_cop_usd = 3600.0  # 1 USD = 3600 COP
# tasa_tienda_bs_usd = 4.5  # 1 USD = 4.5 Bs (example)
# price_in_cop = 4500
# price_in_usd = convert_cop_to_usd(price_in_cop, tasa_cop_usd)
# price_in_bs = convert_cop_to_bs(price_in_cop, tasa_cop_usd, tasa_tienda_bs_usd)