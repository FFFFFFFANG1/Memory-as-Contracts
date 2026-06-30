def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    calls = trace.get('tool_calls') or []
    a_name = 'architectural_design_locator'
    h_name = 'historical_structure_identifier'
    # Group tool calls by iteration/step to detect 'same batch'
    batches = {}
    for c in calls:
        key = c.get('iteration')
        if key is None:
            key = c.get('index')
        batches.setdefault(key, []).append(c.get('name'))
    a_batches = {k for k,v in batches.items() if a_name in v}
    h_batches = {k for k,v in batches.items() if h_name in v}
    paired = a_batches & h_batches
    a_calls = [c for c in calls if c.get('name')==a_name]
    h_calls = [c for c in calls if c.get('name')==h_name]
    if not a_calls and not h_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No cross-verification tool calls found in trajectory.', 'evidence_refs': []}
    # Check every batch that uses either tool also uses the other
    bad = []
    for k, names in batches.items():
        has_a = a_name in names
        has_h = h_name in names
        if has_a ^ has_h:
            bad.append(k)
    if not paired:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'The two cross-verification tools were never called in the same batch.', 'evidence_refs': []}
    if bad:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Batches {bad} used only one of the required cross-verification tools.', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Both tools appear in the same batch(es) and no unpaired batches detected.', 'evidence_refs': []}
