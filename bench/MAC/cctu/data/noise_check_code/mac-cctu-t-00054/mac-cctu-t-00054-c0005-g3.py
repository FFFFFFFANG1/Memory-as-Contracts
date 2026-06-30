def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    allowed = 'historical_location_finder'
    phase_pat = re.compile(r'preliminary\s*scoping', re.I)
    other_phase_pat = re.compile(r'(phase\s*[2-9]|next phase|later phase|second phase|third phase|verification|analysis phase|synthesis)', re.I)
    in_phase = False
    ever_entered = False
    violations = []
    refs = []
    for i, step in enumerate(traj):
        content = (step.get('content') or '') if isinstance(step, dict) else ''
        if phase_pat.search(content):
            in_phase = True
            ever_entered = True
        if in_phase and other_phase_pat.search(content):
            in_phase = False
        tcs = step.get('tool_calls') or [] if isinstance(step, dict) else []
        for tc in tcs:
            name = tc.get('name') or tc.get('tool_name') or ''
            if in_phase and name and name != allowed:
                violations.append({'step': i, 'tool': name})
                refs.append(f'step {i}: {name}')
    if not ever_entered:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'Could not identify Preliminary Scoping phase boundaries in trajectory.', 'evidence_refs': []}
    if violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Non-allowed tools invoked during Preliminary Scoping: {violations}', 'evidence_refs': refs}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Only historical_location_finder (if any) invoked during Preliminary Scoping phase.', 'evidence_refs': []}
