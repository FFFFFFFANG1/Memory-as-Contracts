def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    if not response.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'empty response', 'evidence_refs': []}
    words = response.split()
    if len(words) > 120:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'word count {} exceeds 120'.format(len(words)), 'evidence_refs': []}
    lines = [ln for ln in response.splitlines() if ln.strip()]
    if not lines:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no content lines', 'evidence_refs': []}
    bullet_re = re.compile(r'^\s*(?:[-*+\u2022]|\d+[.)])\s+')
    bullet_lines = [ln for ln in lines if bullet_re.match(ln)]
    non_bullet = [ln for ln in lines if not bullet_re.match(ln)]
    if not bullet_lines:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no bullet list markers found', 'evidence_refs': []}
    if non_bullet:
        # Allow continuation lines indented under a bullet? Be strict: any non-bullet non-empty line is narrative prose
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'narrative prose or non-bullet lines present: {}'.format(non_bullet[:2]), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'single bullet list within 120 words', 'evidence_refs': []}
