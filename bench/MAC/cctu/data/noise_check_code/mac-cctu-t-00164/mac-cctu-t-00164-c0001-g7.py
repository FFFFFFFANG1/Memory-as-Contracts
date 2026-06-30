def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls observed', 'evidence_refs': []}
    first = calls[0].get('name')
    if first == 'landmark_info_retriever':
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'landmark_info_retriever invoked first before other tools', 'evidence_refs': [{'index': calls[0].get('index'), 'name': first}]}
    return {'observed_followed': False, 'confidence': 'high', 'reason': f'First tool call was {first}, not landmark_info_retriever', 'evidence_refs': [{'index': calls[0].get('index'), 'name': first}]}
