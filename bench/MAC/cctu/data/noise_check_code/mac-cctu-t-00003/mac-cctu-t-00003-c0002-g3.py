def evaluate(trace):
    tool_calls = trace.get('tool_calls', []) or []
    analyzer_tools = {'election_result_analyzer','election_results_analyzer','disaster_impact_analyzer'}
    used_analyzers = set()
    for tc in tool_calls:
        name = tc.get('name','')
        if name in analyzer_tools:
            used_analyzers.add(name)
    election_analyzers_used = used_analyzers & {'election_result_analyzer','election_results_analyzer'}
    if not election_analyzers_used:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No election analyzer tools invoked; cannot determine whether seat counts were retrieved or cross-checked.', 'evidence_refs': []}
    if len(used_analyzers) >= 2:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'Seat counts cross-checked across multiple analyzer tools: {sorted(used_analyzers)}.', 'evidence_refs': list(used_analyzers)}
    return {'observed_followed': False, 'confidence': 'high', 'reason': f'Only one analyzer tool used ({sorted(used_analyzers)}); seat counts not cross-checked against at least two distinct analyzers.', 'evidence_refs': list(used_analyzers)}
