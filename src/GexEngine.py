import math

def calculate_black_scholes_gamma(s, k, t, r, iv, is_call=True):
    """
    Calculates the exact contract Gamma locally.
    s: underlying price, k: strike price, t: days to expiry / 365,
    r: risk-free rate (e.g. 0.04), iv: implied volatility (e.g. 0.35)
    """
    if t <= 0 or iv <= 0:
        return 0.0
        
    d1 = (math.log(s / k) + (r + (iv ** 2) / 2) * t) / (iv * math.sqrt(t))
    # Standard normal probability density function for d1
    pdf_d1 = math.exp(-(d1 ** 2) / 2) / math.sqrt(2 * math.pi)
    
    gamma = pdf_d1 / (s * iv * math.sqrt(t))
    return gamma

def compute_net_gex_profile(underlying_price, chain_data, risk_free_rate=0.04):
    """
    Aggregates the raw option legs into a single exposure number.
    chain_data: List of option contracts directly from the Tradier JSON payload.
    """
    total_gex = 0.0
    gamma_flip_candidate = underlying_price
    
    # Process each contract strike leg systematically
    for contract in chain_data:
        strike = float(contract.get('strike', 0))
        open_interest = int(contract.get('open_interest', 0))
        iv = float(contract.get('greeks', {}).get('ask_iv', 0) or contract.get('greeks', {}).get('mid_iv', 0.20))
        option_type = contract.get('option_type', '').lower()
        
        # Calculate days remaining to expiration format
        expiry_str = contract.get('expiration_date')
        if not expiry_str:
            continue
        try:
            days_to_expiry = (datetime.strptime(expiry_str, "%Y-%m-%d") - datetime.now()).days
            t = max(days_to_expiry, 0.5) / 365.0
        except:
            t = 1.0 / 365.0 # Fallback default to 1 day out
            
        gamma = calculate_black_scholes_gamma(underlying_price, strike, t, risk_free_rate, iv)
        
        # Standard Dealer Hedging Multiplier Assumption:
        # Long Calls create supportive positive gamma; Long Puts create negative gamma acceleration
        contract_gex = open_interest * gamma * 100 * underlying_price
        
        if option_type == 'call':
            total_gex += contract_gex
        elif option_type == 'put':
            total_gex -= contract_gex

    return {
        "net_gex": total_gex,
        "gex_label": "POSITIVE" if total_gex >= 0 else "NEGATIVE"
    }
