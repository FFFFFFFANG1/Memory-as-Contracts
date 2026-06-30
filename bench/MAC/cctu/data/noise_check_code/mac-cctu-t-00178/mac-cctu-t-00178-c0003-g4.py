def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    if not resp.endswith('[Itinerary Complete]'):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'missing [Itinerary Complete] marker at end', 'evidence_refs': [resp[-60:]]}
    lines = [l.rstrip() for l in resp.splitlines() if l.strip()]
    bullets = [l for l in lines if re.match(r'^\s*([-*\u2022]|\d+[.)])\s+', l)]
    if not bullets:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no bulleted itinerary detected', 'evidence_refs': lines[:5]}
    date_re = re.compile(r'(\d{1,2}[\-/ ].*?\d{1,2}|\b\w+\s+\d{1,2}\s*[-\u2013]\s*\w*\s*\d{1,2}|\b\d{4}\b.*\d{4}|\w+\s+\d+\s*[-\u2013]\s*\d+)', re.I)
    ok = 0
    bad = []
    for b in bullets:
        body = re.sub(r'^\s*([-*\u2022]|\d+[.)])\s+', '', b)
        has_date = bool(date_re.search(body))
        parts = re.split(r'[,;|\u2013\-]| - ', body)
        if has_date and len(parts) >= 3:
            ok += 1
        else:
            bad.append(body[:120])
    if ok == 0:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'bullets do not show city/date-range/venue ordering', 'evidence_refs': bad[:3]}
    if bad:
        return {'observed_followed': False, 'confidence': 'low', 'reason': 'some bullets missing required fields', 'evidence_refs': bad[:3]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'bulleted itinerary with city/date/venue and end marker', 'evidence_refs': bullets[:3]}
