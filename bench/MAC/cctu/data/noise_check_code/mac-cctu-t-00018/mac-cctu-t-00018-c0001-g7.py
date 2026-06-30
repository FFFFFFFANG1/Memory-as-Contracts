def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    iso = re.compile(r'^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?')
    m = iso.match(resp)
    if not m:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no ISO-8601 timestamp prefix', 'evidence_refs': [resp[:60]]}
    rest = resp[m.end():]
    # find quoted substrings
    quoted = re.findall(r'"([^"]*)"|\u201c([^\u201d]*)\u201d|\'([^\\\']*)\'', rest)
    date_pat = re.compile(r'\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s*\d{0,4}|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4})\b', re.IGNORECASE)
    bad = []
    for tup in quoted:
        q = next((x for x in tup if x), '')
        if date_pat.search(q):
            # need wrapped in square brackets
            if not (q.strip().startswith('[') and q.strip().endswith(']')):
                bad.append(q)
    if bad:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'quoted date not wrapped in brackets: ' + str(bad[:3]), 'evidence_refs': bad[:3]}
    # also check unquoted but bracketed dates exist when dates referenced; not required if none
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'ISO prefix present; quoted dates bracketed or none', 'evidence_refs': [resp[:40]]}
