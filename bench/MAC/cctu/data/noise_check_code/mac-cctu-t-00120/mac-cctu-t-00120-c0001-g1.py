def evaluate(trace):
    traj = trace.get('trajectory') or []
    found = False
    evidence = []
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        names = [tc.get('name') or (tc.get('function') or {}).get('name') for tc in tcs]
        names = [n for n in names if n]
        if len(set(names)) >= 2:
            found = True
            evidence.append({'step': i, 'tools': names})
            break
    if found:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'Found a turn issuing simultaneous calls to multiple distinct tools.', 'evidence_refs': evidence}
    total_tool_calls = sum(len(s.get('tool_calls') or []) for s in traj)
    if total_tool_calls == 0:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls observed; cannot assess parallel retrieval.', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No single turn contained calls to multiple distinct tool types in parallel.', 'evidence_refs': []}
