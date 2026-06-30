def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    if re.fullmatch(r'[+-]?\d+(?:,\d{3})*(?:\.\d+)?', resp):
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'single numeric value with no prose', 'evidence_refs': [resp]}
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'final response is not a bare numeric value', 'evidence_refs': [resp[:120]]}
