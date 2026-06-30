def evaluate(trace):
    traj = trace.get('trajectory') or []
    tool_steps = [s for s in traj if (s.get('tool_calls') or [])]
    if not tool_steps:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool-calling assistant steps found.', 'evidence_refs': []}
    # Treat the early portion (first up to 3 tool-issuing steps) as Initial Query Triage.
    triage = tool_steps[:3]
    refs = []
    for idx, step in enumerate(triage):
        calls = step.get('tool_calls') or []
        n = len(calls)
        refs.append({'turn_index': idx, 'tool_call_count': n, 'tools': [c.get('name') for c in calls]})
        if n != 1:
            return {'observed_followed': False, 'confidence': 'high', 'reason': f'Triage turn {idx} issued {n} tool calls (expected exactly 1, no parallel).', 'evidence_refs': refs}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Each early/triage assistant turn issued exactly one tool call with no parallel invocations.', 'evidence_refs': refs}
