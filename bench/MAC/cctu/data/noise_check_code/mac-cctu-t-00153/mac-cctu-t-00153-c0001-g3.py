def evaluate(trace):
    tcs = trace.get('tool_calls', []) or []
    val_calls = [t for t in tcs if t.get('name') == 'artwork_valuation_tool']
    bir_calls = [t for t in tcs if t.get('name') == 'building_info_retriever']
    if not val_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No artwork_valuation_tool calls present.', 'evidence_refs': []}
    if not bir_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'{len(val_calls)} artwork_valuation_tool call(s) but no building_info_retriever cross-reference.', 'evidence_refs': [t.get('index') for t in val_calls]}
    if len(bir_calls) < len(val_calls):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'{len(val_calls)} valuations but only {len(bir_calls)} building_info_retriever call(s).', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Each valuation appears paired with a building_info_retriever lookup.', 'evidence_refs': [t.get('index') for t in val_calls + bir_calls]}
