def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no content lines', 'evidence_refs': []}
    bullet_re = re.compile(r'^\s*([-*•+]|\d+[\.)])\s+\S')
    bullet_lines = [ln for ln in lines if bullet_re.match(ln)]
    non_bullet = [ln for ln in lines if not bullet_re.match(ln)]
    if not bullet_lines:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no bullet list detected', 'evidence_refs': []}
    if non_bullet:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'narrative prose present: {non_bullet[:2]}', 'evidence_refs': []}
    if len(bullet_lines) < 1:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'insufficient bullets', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'response is a single bullet list with no surrounding prose', 'evidence_refs': []}
