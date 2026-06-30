def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    lines = resp.splitlines()
    bullet_re = re.compile(r'^\s*([-*+]|\d+[.)])\s+')
    has_bullets = any(bullet_re.match(l) for l in lines)
    has_table = '|' in resp and re.search(r'\|.*\|', resp) is not None
    has_table = has_table or re.search(r'^\s*\|', resp, re.M) is not None
    # paragraph breaks
    paragraphs = [p for p in re.split(r'\n\s*\n', resp) if p.strip()]
    single_paragraph = len(paragraphs) == 1 and not has_bullets and not has_table
    if has_bullets:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'bullet list detected', 'evidence_refs': []}
    if has_table:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'table detected', 'evidence_refs': []}
    if not single_paragraph:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'multiple paragraphs', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'single prose paragraph without tables or bullets', 'evidence_refs': []}
