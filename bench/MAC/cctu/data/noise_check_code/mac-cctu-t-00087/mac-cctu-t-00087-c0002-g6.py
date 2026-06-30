def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    names = [c.get('name') for c in calls]
    target = 'sports_event_winner_retriever'
    target_count = sum(1 for n in names if n == target)
    other = [n for n in names if n != target]
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    lines = [l for l in resp.splitlines() if l.strip()]
    if not lines:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no content lines', 'evidence_refs': []}
    bullet_re = re.compile(r'^\s*([-*+\u2022]|\d+[.)])\s+')
    non_bullet = [l for l in lines if not bullet_re.match(l)]
    bullets_ok = len(non_bullet) == 0 and len(lines) >= 1
    tools_ok = (target_count == 1 and len(other) == 0)
    followed = bullets_ok and tools_ok
    reason = f'target_calls={target_count}, other_tools={other}, bullet_lines={len(lines)-len(non_bullet)}/{len(lines)}'
    return {'observed_followed': bool(followed), 'confidence': 'high', 'reason': reason, 'evidence_refs': []}
