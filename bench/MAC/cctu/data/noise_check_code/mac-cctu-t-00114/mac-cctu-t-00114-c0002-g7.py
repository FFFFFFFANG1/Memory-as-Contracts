def evaluate(trace):
    traj = trace.get('trajectory') or []
    turns = []
    for step in traj:
        tcs = step.get('tool_calls') or []
        if tcs:
            turns.append(len(tcs))
    if not turns:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool-calling turns found.', 'evidence_refs': []}
    bad = [i for i, n in enumerate(turns) if n != 3]
    if bad:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Turn batch sizes {turns}; expected 3 per turn.', 'evidence_refs': bad}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'All {len(turns)} tool-calling turns issued exactly 3 calls.', 'evidence_refs': []}
