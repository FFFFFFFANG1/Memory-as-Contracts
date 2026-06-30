def evaluate(trace):
    traj = trace.get('trajectory') or []
    violations = []
    turns_checked = 0
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if tcs:
            turns_checked += 1
            if len(tcs) > 1:
                violations.append(f'step {i} has {len(tcs)} tool calls')
    final = (trace.get('final_response') or '').strip()
    # Check last assistant step for substantive final answer content alongside no tool call
    has_final_answer = False
    if final and len(final) > 40:
        has_final_answer = True
    if turns_checked == 0 and not trace.get('tool_calls'):
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool activity observed', 'evidence_refs': []}
    if violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(violations), 'evidence_refs': violations}
    if has_final_answer:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'final answer produced while constraint forbids it', 'evidence_refs': [final[:120]]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'each turn used at most one tool call and no premature final answer', 'evidence_refs': []}
