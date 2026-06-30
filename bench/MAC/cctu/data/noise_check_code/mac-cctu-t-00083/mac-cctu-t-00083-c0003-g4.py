def evaluate(trace):
    traj = trace.get('trajectory') or []
    issues = []
    checked = 0
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if not tcs:
            continue
        checked += 1
        content = (step.get('content') or '').strip()
        prior = ''
        if not content and i > 0:
            prior = (traj[i-1].get('content') or '').strip()
        rationale = content or prior
        if not rationale:
            issues.append(f'step {i}: no rationale before tool call')
            continue
        lines = [l for l in rationale.splitlines() if l.strip()]
        if len(lines) != 1:
            issues.append(f'step {i}: rationale not single-line ({len(lines)} lines)')
    if checked == 0:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls found', 'evidence_refs': []}
    if issues:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(issues[:5]), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'all {checked} tool calls preceded by single-line rationale', 'evidence_refs': []}
