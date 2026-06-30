def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls observed', 'evidence_refs': []}
    names = [c.get('name') for c in calls]
    n = len(names)
    if n > 3:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'{n} tool invocations exceed cap of 3', 'evidence_refs': names}
    has_bio = 'historical_figure_locator' in names
    has_cul = 'regional_cuisine_identifier' in names
    if has_bio and has_cul:
        bio_i = names.index('historical_figure_locator')
        cul_i = names.index('regional_cuisine_identifier')
        if bio_i > cul_i:
            return {'observed_followed': False, 'confidence': 'high', 'reason': 'culinary tool called before biographical tool in chain', 'evidence_refs': names}
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'cap respected and biographical precedes culinary', 'evidence_refs': names}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'cap respected ({n}<=3); no biographical-then-culinary chain to check', 'evidence_refs': names}
