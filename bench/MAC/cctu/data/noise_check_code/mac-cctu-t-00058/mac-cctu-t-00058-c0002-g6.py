def evaluate(trace):
    trajectory = trace.get('trajectory') or []
    turns = len(trajectory)
    if turns == 0:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no trajectory available', 'evidence_refs': []}
    if turns < 3:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'interaction turns {turns} below minimum 3', 'evidence_refs': []}
    if turns > 5:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'interaction turns {turns} above maximum 5', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'interaction turns {turns} within [3,5]', 'evidence_refs': []}
