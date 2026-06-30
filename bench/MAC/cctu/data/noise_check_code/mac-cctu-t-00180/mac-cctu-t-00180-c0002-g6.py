def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls to assess ordering.', 'evidence_refs': []}
    names = [c.get('name') for c in calls]
    if 'historical_term_origin_finder' not in names:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'historical_term_origin_finder not invoked; cannot confirm whether a term-origin question arose.', 'evidence_refs': []}
    first = names[0]
    if first == 'historical_term_origin_finder':
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'historical_term_origin_finder was called first.', 'evidence_refs': [{'index': 0, 'name': first}]}
    return {'observed_followed': False, 'confidence': 'high', 'reason': f'historical_term_origin_finder was used but not first; first tool was {first}.', 'evidence_refs': [{'index': 0, 'name': first}]}
