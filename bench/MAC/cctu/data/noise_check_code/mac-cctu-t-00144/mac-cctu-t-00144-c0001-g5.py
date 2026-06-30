def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    if not response.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'empty final response', 'evidence_refs': []}
    lines = response.splitlines()
    bullet_re = re.compile(r'^\s*(?:[-*+]\s+|\d+[.)]\s+)(.+)$')
    bullets = []
    for ln in lines:
        m = bullet_re.match(ln)
        if m:
            text = m.group(1).strip()
            if text:
                bullets.append(text)
    if len(bullets) < 1:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no markdown bullet markers found', 'evidence_refs': []}
    if len(bullets) < 3:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'only {len(bullets)} bullet(s); need at least 3', 'evidence_refs': []}
    norm = [re.sub(r'\s+', ' ', b.lower()).strip() for b in bullets]
    if len(set(norm)) < 3:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'bullets are not distinct', 'evidence_refs': []}
    short = [b for b in bullets if len(b.split()) < 3]
    if len(short) > len(bullets) - 3:
        return {'observed_followed': False, 'confidence': 'low', 'reason': 'bullets too short to summarize events', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'{len(bullets)} distinct markdown bullets present', 'evidence_refs': []}
