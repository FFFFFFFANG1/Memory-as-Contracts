def evaluate(trace):
    political_tools = {'election_result_analyzer','historical_event_finder','political_event_search'}
    calls = trace.get('tool_calls') or []
    used = set()
    successful = set()
    for c in calls:
        name = c.get('name')
        if name in political_tools:
            used.add(name)
            res = c.get('result')
            if res is not None and res != '' and 'error' not in str(res).lower()[:40]:
                successful.add(name)
    final = (trace.get('final_response') or '').strip()
    if not final:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'no final response', 'evidence_refs':[]}
    if len(successful) >= 2:
        return {'observed_followed': True, 'confidence':'low', 'reason':f'at least two distinct political-fact tools returned data: {sorted(successful)}; cross-check plausible', 'evidence_refs': sorted(successful)}
    if len(used) >= 2:
        return {'observed_followed': True, 'confidence':'low', 'reason':f'two distinct political tools invoked: {sorted(used)}', 'evidence_refs': sorted(used)}
    if len(used) == 1:
        return {'observed_followed': False, 'confidence':'medium', 'reason':f'only one political-source tool used: {sorted(used)}; cannot cross-check', 'evidence_refs': sorted(used)}
    return {'observed_followed': None, 'confidence':'unknown', 'reason':'no political-source tool calls observed; cannot determine if facts were cross-checked', 'evidence_refs': []}
