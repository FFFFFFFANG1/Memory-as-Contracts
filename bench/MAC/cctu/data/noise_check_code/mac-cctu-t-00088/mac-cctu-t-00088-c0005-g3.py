def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty final response', 'evidence_refs': []}
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no content lines', 'evidence_refs': []}
    bullet_re = re.compile(r'^\s*([-*+\u2022]|\d+[.)])\s+')
    bullet_lines = [l for l in lines if bullet_re.match(l)]
    non_bullet = [l for l in lines if not bullet_re.match(l)]
    if not bullet_lines:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no bulleted list detected', 'evidence_refs': [lines[0][:80]]}
    if non_bullet:
        # allow a single header line that is short and not prose-like? Strict: any non-bullet content line fails
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'prose/non-bullet lines present', 'evidence_refs': [l[:80] for l in non_bullet[:3]]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'all content lines are bullets', 'evidence_refs': [bullet_lines[0][:80]]}
