def evaluate(trace):
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No trajectory available', 'evidence_refs': []}
    turns = [s for s in traj if (s.get('role') in (None, 'assistant')) or s.get('tool_calls') or s.get('content')]
    n = len(turns) if turns else len(traj)
    if n <= 5:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'{n} interaction turns observed, within 5-turn limit', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'high', 'reason': f'{n} interaction turns observed, exceeds 5-turn limit', 'evidence_refs': []}
