def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    low = text.lower()
    forbidden = ['tropical', 'temperate']
    hits = [w for w in forbidden if re.search(r'\b'+w+r'\b', low)]
    if hits:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'references forbidden basin descriptor(s): {hits}', 'evidence_refs': []}
    # Check measurements: look for numeric+unit patterns
    unit_patterns = re.findall(r'\b\d+(?:\.\d+)?\s*(centimeters?|cm|millimeters?|mm|meters?|m|kilometers?|km|inches|in|feet|ft|yards?|yd|miles?)\b', low)
    if not unit_patterns:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'no explicit measurements found to assess units', 'evidence_refs': []}
    non_cm = [u for u in unit_patterns if u not in ('cm','centimeter','centimeters')]
    if non_cm:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'measurements not in centimeters: {non_cm}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'measurements in cm and no tropical/temperate basin reference', 'evidence_refs': []}
