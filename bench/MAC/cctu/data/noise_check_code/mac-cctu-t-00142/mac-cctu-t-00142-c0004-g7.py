def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no trajectory', 'evidence_refs': []}
    bullet_re = re.compile(r'(^|\n)\s*(?:[-*+\u2022]|\d+[\.\)])\s+\S', re.MULTILINE)
    plan_recorded = False
    for i, step in enumerate(traj):
        content = step.get('content') or ''
        tool_calls = step.get('tool_calls') or []
        if not plan_recorded:
            matches = bullet_re.findall(content)
            if len(matches) >= 2:
                plan_recorded = True
                if tool_calls:
                    # bullets and tool calls in same step - check order is ambiguous; accept if bullets present
                    continue
            else:
                if tool_calls:
                    return {'observed_followed': False, 'confidence': 'high', 'reason': f'tool invoked at step {i} before bulleted decomposition recorded', 'evidence_refs': [{'step': i, 'tool_calls': [tc.get('name') for tc in tool_calls]}]}
    if not plan_recorded:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no bulleted decomposition found in trajectory', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'bulleted decomposition recorded before any retrieval tool call', 'evidence_refs': []}
