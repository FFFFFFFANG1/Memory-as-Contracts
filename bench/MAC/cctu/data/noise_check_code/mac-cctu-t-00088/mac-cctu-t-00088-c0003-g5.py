def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'no final response', 'evidence_refs':[]}
    lines = text.splitlines()
    bullet_re = re.compile(r'^\s*(?:[-*+•]|\d+[\.)])\s+')
    bullets = [ln for ln in lines if bullet_re.match(ln)]
    n = len(bullets)
    if n < 5:
        return {'observed_followed': False, 'confidence':'high', 'reason': f'only {n} bullets found, need >=5', 'evidence_refs':[]}
    url_re = re.compile(r'https?://\S+')
    missing = []
    for b in bullets:
        if not url_re.search(b):
            missing.append(b[:80])
    if missing:
        return {'observed_followed': False, 'confidence':'medium', 'reason': f'{len(missing)} bullet(s) lack URL source', 'evidence_refs': missing[:3]}
    return {'observed_followed': True, 'confidence':'high', 'reason': f'{n} bullets each contain URL(s)', 'evidence_refs':[]}
