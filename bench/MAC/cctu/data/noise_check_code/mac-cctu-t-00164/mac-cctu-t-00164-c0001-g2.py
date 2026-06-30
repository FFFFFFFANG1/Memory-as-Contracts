def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls in trajectory', 'evidence_refs': []}
    target = 'aquatic_species_catalog'
    others = [i for i, c in enumerate(calls) if c.get('name') != target]
    aquatic_idx = [i for i, c in enumerate(calls) if c.get('name') == target]
    if not others:
        return {'observed_followed': True, 'confidence': 'low', 'reason': 'only aquatic_species_catalog used; nothing to cross-verify', 'evidence_refs': []}
    if not aquatic_idx:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'other tools were called but aquatic_species_catalog was never invoked for cross-verification', 'evidence_refs': [c.get('name') for c in calls]}
    unverified = []
    for oi in others:
        if not any(ai > oi for ai in aquatic_idx):
            unverified.append((oi, calls[oi].get('name')))
    if unverified:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'tool responses not followed by aquatic_species_catalog cross-verification: {unverified}', 'evidence_refs': [n for _, n in unverified]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'each non-aquatic tool call is followed by an aquatic_species_catalog call', 'evidence_refs': []}
