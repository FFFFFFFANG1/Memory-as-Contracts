def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty final response', 'evidence_refs': []}
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no content lines', 'evidence_refs': []}
    bullet_re = re.compile(r'^\s*([-*+•]|\d+\.)\s+(.*)$')
    iso_re = re.compile(r'^(\d{4}(-\d{2}(-\d{2})?)?)(\s|:|\s*[-–—])')
    bad = []
    good = 0
    for ln in lines:
        m = bullet_re.match(ln)
        if not m:
            bad.append(ln)
            continue
        rest = m.group(2).strip()
        if not iso_re.match(rest):
            bad.append(ln)
            continue
        good += 1
    if good == 0:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no bulleted ISO-dated items found', 'evidence_refs': lines[:3]}
    if bad:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'lines not following bulleted ISO-date format', 'evidence_refs': bad[:3]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'all lines are bulleted ISO-dated items', 'evidence_refs': []}
