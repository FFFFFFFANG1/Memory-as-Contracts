def evaluate(trace):
    traj = trace.get('trajectory') or []
    hlf_steps = []
    hsa_steps = []
    same_step = False
    for i, step in enumerate(traj):
        calls = step.get('tool_calls') or []
        names = [ (c.get('name') or c.get('tool_name')) for c in calls ]
        has_hlf = 'historical_landmark_finder' in names
        has_hsa = 'habitat_species_associator' in names
        if has_hlf:
            hlf_steps.append(i)
        if has_hsa:
            hsa_steps.append(i)
        if has_hlf and has_hsa:
            same_step = True
    if not hsa_steps:
        if not hlf_steps:
            return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'Neither tool invoked.', 'evidence_refs': []}
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'habitat_species_associator never called; ordering vacuously satisfied.', 'evidence_refs': []}
    if same_step:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Both tools issued in the same action step.', 'evidence_refs': []}
    first_hsa = hsa_steps[0]
    preceding_hlf = [s for s in hlf_steps if s < first_hsa]
    if not preceding_hlf:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'habitat_species_associator invoked without any prior historical_landmark_finder call.', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'historical_landmark_finder preceded habitat_species_associator and they were not in the same step.', 'evidence_refs': []}
