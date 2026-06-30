def evaluate(trace):
    retrievers = {'earthquake_event_retriever','event_data_retriever','game_release_finder','historical_event_data_extractor','historical_event_finder','historical_event_locator','historical_event_retriever','sports_event_winner_retriever'}
    calls = trace.get('tool_calls') or []
    used = set()
    for c in calls:
        n = c.get('name')
        if n in retrievers:
            used.add(n)
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls recorded; cannot verify cross-checking.', 'evidence_refs': []}
    if len(used) >= 2:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'Used {len(used)} independent retriever tools: {sorted(used)}.', 'evidence_refs': sorted(used)}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Only {len(used)} retriever tool(s) used; cross-checking against two independent retrievers not evidenced.', 'evidence_refs': sorted(used)}
