def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls') or []
    final = (trace.get('final_response') or '').strip()
    n = len(tool_calls)
    if n > 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Used {n} tool calls, exceeds limit of 2.', 'evidence_refs': []}
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response to inspect.', 'evidence_refs': []}
    lines = [ln for ln in final.splitlines() if ln.strip()]
    if not lines:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'Empty content.', 'evidence_refs': []}
    bullet_re = re.compile(r'^\s*(?:[-*+\u2022]|\d+[.)])\s+')
    bullet_lines = [ln for ln in lines if bullet_re.match(ln)]
    non_bullet = [ln for ln in lines if not bullet_re.match(ln)]
    # Allow a single short heading/intro line at most
    if len(bullet_lines) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Response does not appear to be a bulleted outline.', 'evidence_refs': []}
    if len(non_bullet) > 1:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Response contains {len(non_bullet)} non-bullet lines beyond an optional heading.', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'{n} tool calls and bulleted outline format.', 'evidence_refs': []}
