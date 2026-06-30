def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found in trajectory.', 'evidence_refs': []}
    first = calls[0]
    name = first.get('name')
    if name == 'unread_message_counter':
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'First tool call is unread_message_counter.', 'evidence_refs': [{'index': first.get('index'), 'name': name}]}
    return {'observed_followed': False, 'confidence': 'high', 'reason': f'First tool call was {name!r}, not unread_message_counter.', 'evidence_refs': [{'index': first.get('index'), 'name': name}]}
