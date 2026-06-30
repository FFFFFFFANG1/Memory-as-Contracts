def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    if not response.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    # Find all numeric figures in the response
    # Pattern: numbers (int or decimal), possibly with commas
    num_pattern = re.compile(r'\d+(?:[,\d]*\d)?(?:\.\d+)?')
    matches = list(num_pattern.finditer(response))
    if not matches:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no numeric figures found', 'evidence_refs': []}
    missing = []
    for m in matches:
        end = m.end()
        tail = response[end:end+5]
        if not re.match(r'\s*km\b', tail, re.IGNORECASE):
            missing.append(m.group(0))
    if missing:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'numbers without " km" suffix: ' + ', '.join(missing[:5]), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'all numeric figures suffixed with km', 'evidence_refs': []}
