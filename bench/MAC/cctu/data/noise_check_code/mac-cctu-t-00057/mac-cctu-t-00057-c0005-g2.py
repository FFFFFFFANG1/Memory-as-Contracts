def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found in trajectory.', 'evidence_refs': []}
    first = calls[0]
    name = first.get('name')
    if name != 'cultural_culinary_info':
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'First tool call was {name!r}, not cultural_culinary_info.', 'evidence_refs': [{'index': first.get('index'), 'name': name}]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'cultural_culinary_info was invoked first; caching/reuse not directly verifiable from trace.', 'evidence_refs': [{'index': first.get('index'), 'name': name}]}
