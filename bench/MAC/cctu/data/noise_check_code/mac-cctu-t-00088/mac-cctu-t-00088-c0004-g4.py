def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    bullet_pat = re.compile(r'^\s*([-*+•]|\d+[.)])\s+\S')
    bullets = [l for l in lines if bullet_pat.match(l)]
    if len(bullets) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Final response is not a bulleted list of attributes', 'evidence_refs': lines[:5]}
    non_bullet_content = [l for l in lines if not bullet_pat.match(l) and not l.endswith(':') and len(l) > 20]
    if len(non_bullet_content) > len(bullets):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Final deliverable contains substantial prose rather than bullets per attribute', 'evidence_refs': non_bullet_content[:3]}
    multi_attr = [b for b in bullets if b.count(',') >= 2 or ';' in b]
    if len(multi_attr) >= max(2, len(bullets)//2):
        return {'observed_followed': False, 'confidence': 'low', 'reason': 'Bullets appear to bundle multiple attributes rather than one per bullet', 'evidence_refs': multi_attr[:3]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'Final response is a bulleted list with {len(bullets)} bullets', 'evidence_refs': bullets[:5]}
