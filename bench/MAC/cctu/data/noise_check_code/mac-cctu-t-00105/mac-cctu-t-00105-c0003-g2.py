def evaluate(trace):
    retrieval_tools = {
        'astronomical_discovery_info','constitutional_info_retriever',
        'historical_crime_analyzer','historical_event_and_fact_retriever',
        'historical_event_facts','historical_event_tool',
        'political_union_info','unified_population_data_retriever'
    }
    calls = trace.get('tool_calls') or []
    used = set()
    refs = []
    for c in calls:
        name = c.get('name')
        if name in retrieval_tools:
            used.add(name)
            refs.append({'tool': name, 'index': c.get('index')})
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found in trace.', 'evidence_refs': []}
    if len(used) >= 3:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'Used {len(used)} distinct retrieval tools: {sorted(used)}.', 'evidence_refs': refs}
    return {'observed_followed': False, 'confidence': 'high', 'reason': f'Only {len(used)} distinct retrieval tools used: {sorted(used)}; need >=3.', 'evidence_refs': refs}
