def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    lines = text.splitlines()
    bullet_re = re.compile(r'^\s*([-*+•]|\d+[.)])\s+')
    bullets = [l for l in lines if bullet_re.match(l)]
    has_bullets = len(bullets) >= 2
    tool_calls = trace.get('tool_calls') or []
    raw_outputs = []
    for tc in tool_calls:
        r = tc.get('result')
        if r is None:
            continue
        s = r if isinstance(r, str) else str(r)
        if s and len(s.strip()) > 10:
            raw_outputs.append(s.strip())
    if not raw_outputs:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool outputs to verify verbatim append', 'evidence_refs': []}
    appended = 0
    for s in raw_outputs:
        snippet = s[:120].strip()
        if snippet and snippet in text:
            appended += 1
    verbatim_ok = appended >= max(1, len(raw_outputs)//2)
    followed = has_bullets and verbatim_ok
    return {'observed_followed': bool(followed), 'confidence': 'medium', 'reason': f'bullets={len(bullets)} verbatim_matches={appended}/{len(raw_outputs)}', 'evidence_refs': []}
