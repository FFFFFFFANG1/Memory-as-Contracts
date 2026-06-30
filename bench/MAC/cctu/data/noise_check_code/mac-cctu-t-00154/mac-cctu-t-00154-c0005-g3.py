def evaluate(trace):
    traj = trace.get('trajectory') or []
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls observed', 'evidence_refs': []}
    # Check serialization: no step should have >1 tool_call in parallel
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if len(tcs) > 1:
            return {'observed_followed': False, 'confidence': 'high', 'reason': f'step {i} issued {len(tcs)} parallel tool calls', 'evidence_refs': [f'step:{i}']}
    # Check ordering: historical_residence_locator before any biographical_info_finder
    first_bio = None
    first_res = None
    for idx, c in enumerate(calls):
        name = c.get('name')
        if name == 'biographical_info_finder' and first_bio is None:
            first_bio = idx
        if name == 'historical_residence_locator' and first_res is None:
            first_res = idx
    if first_bio is None:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'serialized and no biographical_info_finder call to violate order', 'evidence_refs': []}
    if first_res is None or first_res > first_bio:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'biographical_info_finder invoked before historical_residence_locator', 'evidence_refs': [f'bio_idx:{first_bio}', f'res_idx:{first_res}']}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'tool calls serialized and historical_residence_locator preceded biographical_info_finder', 'evidence_refs': [f'res_idx:{first_res}', f'bio_idx:{first_bio}']}
