def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    if re.fullmatch(r'[+-]?\d+', resp):
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'response is a single integer', 'evidence_refs': [resp]}
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'response is not a single bare integer', 'evidence_refs': [resp[:120]]}
