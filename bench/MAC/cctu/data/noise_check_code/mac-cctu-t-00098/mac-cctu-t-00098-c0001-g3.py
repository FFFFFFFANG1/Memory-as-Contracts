def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No tool calls found.', 'evidence_refs': []}
    names = [c.get('name') for c in calls]
    sdr_calls = [i for i,n in enumerate(names) if n == 'species_data_retriever']
    if not sdr_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'species_data_retriever not used as primary source.', 'evidence_refs': names}
    distinct = set(names)
    if len(calls) < 2 or len(distinct) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Fewer than two independent tool calls for verification.', 'evidence_refs': names}
    first_non_meta = next((n for n in names if n), None)
    primary_ok = (names[0] == 'species_data_retriever') or (sdr_calls and sdr_calls[0] <= 1)
    if not primary_ok:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'species_data_retriever used but not clearly primary.', 'evidence_refs': names}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'species_data_retriever used as primary with additional independent tool call(s).', 'evidence_refs': names}
