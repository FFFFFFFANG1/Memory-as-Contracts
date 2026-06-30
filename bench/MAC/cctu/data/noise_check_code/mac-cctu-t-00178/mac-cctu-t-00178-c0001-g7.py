def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    # Find intermediate assistant messages (those that have content and follow tool calls)
    intermediates = []
    saw_tool = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = (step.get('content') or '').strip()
        if tcs:
            saw_tool = True
        if saw_tool and content and step is not traj[-1]:
            intermediates.append(step)
    if not intermediates:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No intermediate observation messages found', 'evidence_refs': []}
    tool_calls = trace.get('tool_calls') or []
    payloads = []
    for tc in tool_calls:
        r = tc.get('result')
        if r is not None:
            payloads.append(str(r))
    bad = []
    for i, step in enumerate(intermediates):
        text = step.get('content') or ''
        # Numbered bullet list check: at least one line like '1.' or '1)'
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        numbered = sum(1 for l in lines if re.match(r'^\d+[\.\)]\s+', l))
        if numbered < 1:
            bad.append(f'step {i}: no numbered bullets')
            continue
        # Raw payload verbatim attached
        has_payload = any(p and p in text for p in payloads)
        if not has_payload:
            bad.append(f'step {i}: raw payload not verbatim')
    if bad:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(bad), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Intermediate observations numbered with raw payloads', 'evidence_refs': []}
