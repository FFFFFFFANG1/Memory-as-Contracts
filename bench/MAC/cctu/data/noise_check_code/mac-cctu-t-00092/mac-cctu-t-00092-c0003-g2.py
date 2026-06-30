def evaluate(trace):
    import re
    tool_names = {tc.get('name') for tc in trace.get('tool_calls', [])}
    used = [t for t in ('biographical_data_search','person_location_finder') if t in tool_names]
    if not used:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'Neither relevant tool was called; constraint not triggered.', 'evidence_refs': []}
    text = trace.get('final_response','') or ''
    for step in trace.get('trajectory', []):
        c = step.get('content')
        if isinstance(c, str):
            text += '\n' + c
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No textual content to inspect.', 'evidence_refs': []}
    lines = text.splitlines()
    bullet_re = re.compile(r'^\s*([\-\*\u2022]|\d+[\.)])\s+')
    annotated = []
    for t in used:
        pat = re.compile(r'\(\s*' + re.escape(t) + r'\s*\)')
        bullet_hits = [ln for ln in lines if bullet_re.match(ln) and pat.search(ln)]
        any_mention = bool(pat.search(text))
        annotated.append((t, bool(bullet_hits), any_mention))
    missing_annotation = [t for t,_,m in annotated if not m]
    not_bulleted = [t for t,b,m in annotated if m and not b]
    if missing_annotation:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Tool(s) used but never annotated in parentheses: {missing_annotation}', 'evidence_refs': []}
    if not_bulleted:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Findings from {not_bulleted} not formatted as bullet lines with source annotation.', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Intermediate findings appear as bullet lines with source tool annotated in parentheses.', 'evidence_refs': []}
