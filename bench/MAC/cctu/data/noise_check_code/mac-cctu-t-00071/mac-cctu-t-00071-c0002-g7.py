def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found', 'evidence_refs': []}
    if len(calls) < 2:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'Not a multi-hop lookup (fewer than 2 tool calls)', 'evidence_refs': []}
    first = calls[0].get('name')
    if first == 'location_identifier':
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'First tool call is location_identifier', 'evidence_refs': [{'index': calls[0].get('index'), 'name': first}]}
    return {'observed_followed': False, 'confidence': 'high', 'reason': f'First tool call was {first}, not location_identifier', 'evidence_refs': [{'index': calls[0].get('index'), 'name': first}]}
