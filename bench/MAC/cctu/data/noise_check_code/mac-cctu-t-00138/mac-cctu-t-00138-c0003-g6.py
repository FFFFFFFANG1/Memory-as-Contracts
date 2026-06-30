def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    lines = [l for l in text.split('\n') if l.strip()]
    bullet_re = re.compile(r'^(\s*)([-*+\u2022]|\d+[.)])\s+')
    bullets = [(len(m.group(1)), l) for l in lines if (m := bullet_re.match(l))]
    if len(bullets) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no bullet list detected', 'evidence_refs': []}
    indents = sorted({b[0] for b in bullets})
    if len(indents) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no indentation hierarchy found', 'evidence_refs': [str(b[1]) for b in bullets[:5]]}
    # Need at least one parent followed by a deeper-indented child
    has_parent_child = False
    for i in range(len(bullets)-1):
        if bullets[i][0] < bullets[i+1][0]:
            has_parent_child = True
            break
    if not has_parent_child:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no parent->indented child pattern', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'hierarchical bullet list with indented children present', 'evidence_refs': []}
