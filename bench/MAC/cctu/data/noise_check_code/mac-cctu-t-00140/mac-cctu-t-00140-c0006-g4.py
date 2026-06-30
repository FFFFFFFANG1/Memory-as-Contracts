def evaluate(trace):
    import re
    r = (trace.get('final_response') or '').strip()
    if not r:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    length_ok = len(r) <= 280
    m = re.search(r'#\w+\s*$', r)
    hashtag_ok = bool(m)
    ok = length_ok and hashtag_ok
    return {'observed_followed': ok, 'confidence': 'high', 'reason': f'len={len(r)} length_ok={length_ok} hashtag_ok={hashtag_ok}', 'evidence_refs': []}
