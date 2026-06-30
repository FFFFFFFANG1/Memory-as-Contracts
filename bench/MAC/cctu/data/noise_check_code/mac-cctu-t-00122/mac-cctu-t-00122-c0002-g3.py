def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    metric_units = r'(?:kg|g|mg|kilograms?|grams?|milligrams?|l|ml|liters?|litres?|milliliters?|millilitres?|kl|t|tonnes?|metric tons?)'
    imperial_units = r'(?:lbs?|pounds?|oz|ounces?|gal|gallons?|qt|quarts?|pt|pints?|cups?|tbsp|tsp|tablespoons?|teaspoons?|fl\s*oz)'
    # find numeric values followed by units
    num_pat = re.compile(r'(\d+(?:[\.,]\d+)?)\s*(' + metric_units + r'|' + imperial_units + r')\b', re.IGNORECASE)
    matches = num_pat.findall(text)
    if not matches:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'no inventory totals with units detected', 'evidence_refs': []}
    bad = []
    for num, unit in matches:
        u = unit.lower()
        if re.fullmatch(imperial_units, u, re.IGNORECASE):
            bad.append(f'imperial unit used: {num} {unit}')
            continue
        # check two decimals
        normalized = num.replace(',', '.')
        if '.' not in normalized:
            bad.append(f'no decimals: {num} {unit}')
        else:
            dec = normalized.split('.')[1]
            if len(dec) != 2:
                bad.append(f'wrong decimal precision: {num} {unit}')
    if bad:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(bad[:5]), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'all totals metric with 2 decimals', 'evidence_refs': []}
