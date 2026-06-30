def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        for step in reversed(trace.get('trajectory') or []):
            c = step.get('content') or ''
            if c.strip():
                text = c
                break
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no response text', 'evidence_refs': []}
    lines = [ln.rstrip() for ln in text.splitlines()]
    bullet_re = re.compile(r'^\s*(?:[-*•]|\d+[.)])\s+(.*)$')
    bullets = []
    for ln in lines:
        m = bullet_re.match(ln)
        if m:
            bullets.append(m.group(1))
    if not bullets:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no bulleted incident lines found', 'evidence_refs': []}
    code_re = re.compile(r'^[A-Z]{4}\b')
    bad_bullets = [b for b in bullets if not code_re.match(b.strip().strip('*_`'))]
    if bad_bullets:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'{len(bad_bullets)} bullet(s) do not start with a 4-letter airport identifier: {bad_bullets[:2]}', 'evidence_refs': []}
    agg_patterns = [r'\btotal\b', r'\baverage\b', r'\bmean\b', r'\bsum\b', r'\baggregate\b', r'\boverall\b', r'\bcount of\b', r'\bnumber of incidents\b', r'\bpercentage\b', r'%']
    lowered = text.lower()
    hits = [p for p in agg_patterns if re.search(p, lowered)]
    if hits:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'contains quantitative aggregate terms: {hits}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'{len(bullets)} bullets start with 4-letter ID and no aggregate terms detected', 'evidence_refs': []}
