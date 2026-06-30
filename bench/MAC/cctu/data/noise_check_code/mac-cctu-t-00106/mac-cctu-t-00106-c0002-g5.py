def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    lines = [l.rstrip() for l in text.splitlines()]
    bullet_re = re.compile(r'^\s*(?:[-*+\u2022]|\d+[.)])\s+\S')
    bullets = [l for l in lines if bullet_re.match(l)]
    n = len(bullets)
    if n >= 5:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'found {n} bulleted items', 'evidence_refs': bullets[:5]}
    return {'observed_followed': False, 'confidence': 'high', 'reason': f'only {n} bullet items detected; need >=5', 'evidence_refs': bullets}
