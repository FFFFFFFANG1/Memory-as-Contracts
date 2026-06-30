def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found in trajectory.', 'evidence_refs': []}
    first = calls[0]
    name = first.get('name') or first.get('tool_name')
    if name == 'desert_city_locator':
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'First tool call is desert_city_locator.', 'evidence_refs': [{'index': first.get('index', 0), 'name': name}]}
    return {'observed_followed': False, 'confidence': 'high', 'reason': f'First tool call was {name}, not desert_city_locator.', 'evidence_refs': [{'index': first.get('index', 0), 'name': name}]}
