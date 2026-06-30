def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found', 'evidence_refs': []}
    names = [c.get('name') for c in calls]
    if 'gym_membership_pricing_tool' not in names:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'gym_membership_pricing_tool was not used as primary source', 'evidence_refs': names}
    # Find first call's tool
    first = calls[0].get('name')
    if first != 'gym_membership_pricing_tool':
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Primary source should be gym_membership_pricing_tool but first call was {first}', 'evidence_refs': names}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'gym_membership_pricing_tool used first as primary source; other tools appear supplementary', 'evidence_refs': names}
