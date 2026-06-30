def evaluate(trace):
    trajectory = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls in trajectory.', 'evidence_refs': []}
    missing = []
    checked = 0
    for step in trajectory:
        calls = step.get('tool_calls') or []
        if not calls:
            continue
        content = (step.get('content') or '').strip()
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        has_justification = False
        for l in lines:
            low = l.lower()
            if any(k in low for k in ['justif', 'ledger', 'because', 'rationale', 'reason', 'in order to', 'to ']):
                has_justification = True
                break
        if not has_justification and lines:
            # any single short line could count as a one-line justification
            if len(lines) >= 1 and len(lines[0]) <= 240:
                has_justification = True
        for c in calls:
            checked += 1
            if not has_justification:
                missing.append(c.get('name', 'unknown'))
    if checked == 0:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'Could not align tool calls to assistant steps.', 'evidence_refs': []}
    if missing:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'{len(missing)} of {checked} tool invocations lacked a preceding one-line justification: {missing[:3]}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'low', 'reason': f'Each of {checked} tool invocations was preceded by some justification-like content; explicit ledger entries not verifiable from trace.', 'evidence_refs': []}
