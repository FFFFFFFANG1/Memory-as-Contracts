def evaluate(trace):
    calls = trace.get('tool_calls') or []
    location_tools = {'business_locator','countryside_distillery_locator','individual_location_finder','location_identifier','venue_locator'}
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    seen_bartender = False
    seen_award = False
    used_location = any((c.get('name') in location_tools) for c in calls)
    if not used_location and not any(c.get('name') in {'bartender_matcher','award_winner_retriever'} for c in calls):
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no relevant tools invoked', 'evidence_refs': []}
    for i, c in enumerate(calls):
        name = c.get('name')
        if name == 'bartender_matcher':
            seen_bartender = True
        elif name == 'award_winner_retriever':
            seen_award = True
        elif name in location_tools:
            if not (seen_bartender and seen_award):
                return {'observed_followed': False, 'confidence': 'high', 'reason': f'location tool {name} dispatched at index {i} before cross-referencing bartender_matcher and award_winner_retriever', 'evidence_refs': [{'tool_index': i, 'name': name}]}
    if not used_location:
        if seen_bartender and seen_award:
            return {'observed_followed': True, 'confidence': 'medium', 'reason': 'cross-reference observed; no location tool dispatched', 'evidence_refs': []}
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'no location tool dispatched; constraint not exercised', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'bartender_matcher and award_winner_retriever both invoked before any location-resolution tool', 'evidence_refs': []}
