def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    words = re.findall(r"\S+", resp)
    wc = len(words)
    if wc >= 50:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Response has {wc} words (>=50)', 'evidence_refs': [resp[:120]]}
    calc_patterns = [r'\d+\s*[-+\u2212]\s*\d+\s*=', r'=\s*\d+\s*days', r'subtract', r'difference between', r'calculat', r'\d+\s*-\s*\d+\s*\+', r'days between.*=']
    low = resp.lower()
    hits = [p for p in calc_patterns if re.search(p, low)]
    if hits:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Explicit calculation shown: {hits}', 'evidence_refs': [resp[:200]]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'{wc} words, no explicit calculation step detected', 'evidence_refs': [resp[:120]]}
