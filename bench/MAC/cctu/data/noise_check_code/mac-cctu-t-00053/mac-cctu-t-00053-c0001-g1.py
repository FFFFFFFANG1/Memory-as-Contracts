def evaluate(trace):
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no trajectory', 'evidence_refs': []}
    any_tool = False
    violations = []
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if not tcs:
            continue
        any_tool = True
        content = (step.get('content') or '').strip()
        rationale_here = len(content) >= 20
        rationale_prev = False
        if not rationale_here and i > 0:
            prev = (traj[i-1].get('content') or '').strip()
            if (traj[i-1].get('role') in (None, 'assistant')) and len(prev) >= 20 and not (traj[i-1].get('tool_calls')):
                rationale_prev = True
        if not (rationale_here or rationale_prev):
            violations.append(i)
    if not any_tool:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls observed', 'evidence_refs': []}
    if violations:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'tool calls without preceding rationale at steps {violations}', 'evidence_refs': violations}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'each tool call preceded by textual rationale', 'evidence_refs': []}
