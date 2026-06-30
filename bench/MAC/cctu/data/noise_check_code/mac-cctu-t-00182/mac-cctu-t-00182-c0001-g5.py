def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    imperial_patterns = [
        r'\b\d+(?:[\.,]\d+)?\s*(?:feet|foot|ft|ft\.)\b',
        r'\b\d+(?:[\.,]\d+)?\s*(?:inch|inches|in\.)\b',
        r'\b\d+(?:[\.,]\d+)?\s*(?:yard|yards|yd|yds)\b',
        r'\b\d+(?:[\.,]\d+)?\s*(?:mile|miles|mi)\b',
        r'\b\d+(?:[\.,]\d+)?\s*(?:pound|pounds|lbs?)\b',
        r'\b\d+(?:[\.,]\d+)?\s*(?:ounce|ounces|oz)\b',
        r'\b\d+(?:[\.,]\d+)?\s*(?:gallon|gallons|gal)\b',
        r'\b\d+(?:[\.,]\d+)?\s*(?:fahrenheit|°F)\b',
        r"\b\d+(?:[\.,]\d+)?\s*'\s*(?:\d+(?:[\.,]\d+)?\s*\"?)?",
    ]
    found = []
    for pat in imperial_patterns:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            found.append(m.group(0))
    has_numbers = bool(re.search(r'\d', text))
    if not has_numbers:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no numerical outputs found', 'evidence_refs': []}
    if found:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'imperial units detected: ' + ', '.join(found[:5]), 'evidence_refs': found[:5]}
    metric_pat = r'\b\d+(?:[\.,]\d+)?\s*(?:m|meter|meters|metre|metres|km|kilometer|kilometers|cm|centimeter|centimeters|mm|kg|kilogram|kilograms|g|gram|grams|l|liter|liters|litre|litres|°C|celsius)\b'
    metric_found = re.findall(metric_pat, text, flags=re.IGNORECASE)
    if metric_found:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'metric units used, no imperial detected', 'evidence_refs': metric_found[:5]}
    return {'observed_followed': True, 'confidence': 'low', 'reason': 'numbers present but no imperial units detected; unit context unclear', 'evidence_refs': []}
