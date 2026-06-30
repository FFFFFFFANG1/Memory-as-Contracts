def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    forbidden = {'literary_verse_finder','biographical_data_retriever','population_data_retriever','population_data_retriever_v2'}
    names = [c.get('name') for c in calls]
    used_forbidden = [n for n in names if n in forbidden]
    if used_forbidden:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'forbidden tools used: {used_forbidden}', 'evidence_refs': names[:5]}
    if len(names) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'fewer than 2 tool calls', 'evidence_refs': names}
    first_two = names[:2]
    expected = ['ice_sheet_thickness_calculator','highest_point_locator']
    if first_two == expected:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'first two calls match required order, no forbidden tools', 'evidence_refs': first_two}
    return {'observed_followed': False, 'confidence': 'high', 'reason': f'first two calls were {first_two}, expected {expected}', 'evidence_refs': first_two}
