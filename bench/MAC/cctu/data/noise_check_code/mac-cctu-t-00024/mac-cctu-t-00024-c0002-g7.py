def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').rstrip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    lines = [l for l in resp.split('\n') if l.strip()]
    if len(lines) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no separate line beneath main answer', 'evidence_refs': []}
    tail = '\n'.join(lines[-3:])
    date_patterns = [
        r'\b\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{3,4}\b',
        r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s*\d{3,4}\b',
        r'\b\d{4}-\d{2}-\d{2}\b',
        r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',
        r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{3,4}\b',
    ]
    has_date = any(re.search(p, tail, re.IGNORECASE) for p in date_patterns)
    has_name = bool(re.search(r'\b[A-Z][a-zA-Z\.\-]+(?:\s+(?:de|van|von|del|of|the)\s+|\s+)[A-Z][a-zA-Z\.\-]+', tail))
    if has_date and has_name:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'successor name and date present on separate line', 'evidence_refs': []}
    missing = []
    if not has_name: missing.append('name')
    if not has_date: missing.append('date')
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'missing on separate line: ' + ', '.join(missing), 'evidence_refs': []}
