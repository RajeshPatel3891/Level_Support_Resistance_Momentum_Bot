def detect_support(ticker, price, prev_low, volume, avg_volume):
    # Support strategy: Price holding above previous low with volume surge
    if price > prev_low and volume > avg_volume:
        return "SUPPORT_CONFIRMED"
    return "NONE"

def get_call_confidence(ticker, active_alerts):
    # Confidence score for Calls:
    score = 4
    if len(active_alerts) > 1:
        score += 3
    score += 3
    return score
