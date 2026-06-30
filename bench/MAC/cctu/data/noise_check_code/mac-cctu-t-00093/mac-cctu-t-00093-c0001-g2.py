def evaluate(trace):
    traj = trace.get('trajectory') or []
    rounds = len(traj)
    if rounds == 0:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No trajectory steps found', 'evidence_refs': []}
    if rounds <= 12:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'Trajectory used {rounds} rounds, within the 12-round allowance; no order or punctuation enforcement required', 'evidence_refs': [{'rounds': rounds}]}
    return {'observed_followed': False, 'confidence': 'high', 'reason': f'Trajectory used {rounds} rounds, exceeding the 12-round allowance', 'evidence_refs': [{'rounds': rounds}]}
