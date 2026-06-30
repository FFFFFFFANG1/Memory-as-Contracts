def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty final response', 'evidence_refs': []}
    date_patterns = [
        r'\b\d{4}-\d{2}-\d{2}\b',
        r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',
        r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\b\.?\s*\d{0,4}',
        r'\b(?:19|20)\d{2}\b',
    ]
    location_keys = [r'\bcity\b', r'\bcountry\b', r'\bregion\b', r'\bprovince\b', r'\bstate\b', r'\bdistrict\b', r'\bvillage\b', r'\btown\b', r'\blatitude\b', r'\blongitude\b', r'\blocation\b', r'\baddress\b', r'\bcoordinates\b', r'\bgps\b']
    date_keys = [r'\bdate\b', r'\btimestamp\b', r'\boccurred[_ ]on\b', r'\bwhen\b']
    hits = []
    for pat in date_patterns + location_keys + date_keys:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            hits.append(m.group(0))
    if hits:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'final response contains location/date-like metadata: ' + ', '.join(hits[:5]), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'no obvious location or date metadata detected in final response', 'evidence_refs': []}
