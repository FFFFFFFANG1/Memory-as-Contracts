def evaluate(trace):
    final = str((trace or {}).get('final_response') or '')
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no observable response', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'low', 'reason': 'no deterministic feature checks configured', 'evidence_refs': []}
