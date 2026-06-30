def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    lines = text.splitlines()
    bullet_re = re.compile(r'^\s*(?:[-*+•]|\d+[.)])\s+\S')
    bullets = [ln for ln in lines if bullet_re.match(ln)]
    has_list = len(bullets) >= 3
    low = text.lower()
    defer_terms = ['defer', 'downstream review', 'downstream reviewer', 'reviewer', 'final selection', 'final decision', 'for review', 'pending review', 'leave the final', 'leaves the final', 'final choice']
    defers = any(t in low for t in defer_terms)
    followed = has_list and defers
    return {
        'observed_followed': bool(followed),
        'confidence': 'high' if (has_list and defers) or (not has_list) else 'medium',
        'reason': f'bullets={len(bullets)}, defer_mentioned={defers}',
        'evidence_refs': []
    }
