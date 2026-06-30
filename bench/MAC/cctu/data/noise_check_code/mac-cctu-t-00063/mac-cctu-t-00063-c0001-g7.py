def evaluate(trace):
    import re
    resp = trace.get('final_response') or ''
    if not resp.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    tail = resp.strip()[-400:]
    has_pct = bool(re.search(r'\d{1,3}\s*%', tail))
    # Look for a timestamp-like pattern in the tail
    ts_patterns = [
        r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?',
        r'\d{2}:\d{2}(:\d{2})?\s*(AM|PM|am|pm|UTC|GMT)?',
        r'\d{1,2}/\d{1,2}/\d{2,4}\s*\d{1,2}:\d{2}',
    ]
    has_ts = any(re.search(p, tail) for p in ts_patterns)
    followed = has_pct and has_ts
    return {
        'observed_followed': bool(followed),
        'confidence': 'medium' if followed or (has_pct or has_ts) else 'medium',
        'reason': f'tail has_pct={has_pct} has_ts={has_ts}',
        'evidence_refs': []
    }
