def evaluate(trace):
    tool_calls = trace.get('tool_calls') or []
    retrieval_tools = {
        'event_city_locator','event_metric_finder','landmark_info_retriever',
        'literary_influence_finder','memorial_locator','patent_search_tool',
        'person_profession_locator','population_data_retriever',
        'region_highlight_locator','structure_info_retriever','war_hero_identifier'
    }
    used = []
    for tc in tool_calls:
        name = tc.get('name')
        if name in retrieval_tools:
            used.append(name)
    distinct = set(used)
    if not tool_calls:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'no tool calls recorded', 'evidence_refs':[]}
    if len(distinct) < 2:
        return {'observed_followed': False, 'confidence':'high', 'reason': f'only {len(distinct)} distinct retrieval tool(s) used: {sorted(distinct)}', 'evidence_refs':[]}
    if len(used) < 2:
        return {'observed_followed': False, 'confidence':'high', 'reason':'fewer than two retrieval invocations', 'evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'medium', 'reason': f'{len(distinct)} distinct retrieval tools invoked: {sorted(distinct)}', 'evidence_refs':[]}
