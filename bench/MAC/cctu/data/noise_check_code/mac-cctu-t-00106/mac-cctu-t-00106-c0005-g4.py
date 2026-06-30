def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response to evaluate.', 'evidence_refs': []}
    lines = text.splitlines()
    bullet_re = re.compile(r'^\s*(?:[-*+\u2022]|\d+[.)])\s+\S')
    bullets = [ln for ln in lines if bullet_re.match(ln)]
    count = len(bullets)
    if count == 0:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Final response is not formatted as a bulleted list.', 'evidence_refs': []}
    if count < 5:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Only {count} bulleted entries found; need at least 5.', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'Found {count} bulleted entries in final response.', 'evidence_refs': []}
