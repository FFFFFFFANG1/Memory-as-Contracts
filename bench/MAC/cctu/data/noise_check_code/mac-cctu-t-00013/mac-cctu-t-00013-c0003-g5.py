def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    lines = text.splitlines()
    bullets = [l.strip() for l in lines if re.match(r'^\s*[-*\u2022]\s+', l)]
    if not bullets:
        return {'observed_followed': False, 'confidence':'medium','reason':'no bullet points found','evidence_refs':[]}
    missing = [b for b in bullets if not re.search(r'\([^)]+\)', b)]
    if missing:
        return {'observed_followed': False, 'confidence':'high','reason': f'{len(missing)} bullet(s) missing parenthetical legislative body','evidence_refs': missing[:3]}
    return {'observed_followed': True, 'confidence':'medium','reason': f'{len(bullets)} bullets each include a parenthetical note','evidence_refs': bullets[:3]}
