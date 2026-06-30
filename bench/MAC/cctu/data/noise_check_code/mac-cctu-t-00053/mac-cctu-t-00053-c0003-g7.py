def evaluate(trace):
    tool_calls = trace.get('tool_calls', []) or []
    final = trace.get('final_response', '') or ''
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls observed', 'evidence_refs': []}
    first = tool_calls[0]
    first_name = first.get('name', '')
    if first_name != 'district_identifier':
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'First tool was {first_name}, not district_identifier', 'evidence_refs': [{'index': first.get('index'), 'name': first_name}]}
    missing = []
    for tc in tool_calls:
        result = tc.get('result')
        if result is None:
            continue
        snippet = str(result).strip()
        if not snippet:
            continue
        sample = snippet[:60]
        if sample and sample not in final:
            missing.append({'name': tc.get('name'), 'index': tc.get('index'), 'sample': sample})
    if missing:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Some tool transcripts not embedded verbatim in final response', 'evidence_refs': missing[:5]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'district_identifier first and transcripts appear embedded', 'evidence_refs': []}
