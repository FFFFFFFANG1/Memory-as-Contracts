def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    names = [c.get('name') for c in calls]
    corporate = {'corporate_acquisition_finder', 'corporate_property_info'}
    if names[0] != 'music_info_retriever':
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'first tool was {names[0]}, not music_info_retriever', 'evidence_refs': [0]}
    bio_idx = None
    for i, n in enumerate(names):
        if n == 'biographical_info_retriever':
            bio_idx = i
            break
    for i, n in enumerate(names):
        if n in corporate:
            if bio_idx is None or bio_idx >= i:
                return {'observed_followed': False, 'confidence': 'high', 'reason': f'corporate tool {n} at {i} called before biographical_info_retriever', 'evidence_refs': [i]}
            break
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'music_info_retriever first; biographical_info_retriever precedes any corporate tool', 'evidence_refs': []}
