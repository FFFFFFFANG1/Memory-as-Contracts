def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    tool_names = [str(c.get('name') or '') for c in tool_calls]
    beach_count = sum(1 for n in tool_names if n == 'beach_locator')
    reasons = []
    if beach_count < 1:
        reasons.append('beach_locator not invoked at least once')
    lines = [ln for ln in response.splitlines() if ln.strip()]
    bullet_re = re.compile(r'^\s*([-*+]|\d+[.)])\s+\S')
    bullet_lines = [ln for ln in lines if bullet_re.match(ln)]
    if not lines:
        reasons.append('final response empty')
    elif len(bullet_lines) < 2:
        reasons.append('final response is not a bulleted list')
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'beach_locator invoked and bulleted list present', 'evidence_refs': []}
