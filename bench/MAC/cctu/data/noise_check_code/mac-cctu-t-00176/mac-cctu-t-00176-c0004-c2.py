def evaluate(trace):
    data_tools = {'biographical_info_extractor','chef_dish_associator','factory_locator','historical_site_locator','individual_location_identifier','island_feature_locator','population_data_retriever','production_data_aggregator','protected_area_info','research_location_identifier','restaurant_locator','tourist_statistics_aggregator'}
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no trajectory','evidence_refs':[]}
    first = traj[0]
    tcs = first.get('tool_calls') or []
    if len(tcs) == 0:
        return {'observed_followed': True,'confidence':'medium','reason':'initial turn made no tool calls','evidence_refs':[]}
    if len(tcs) > 1:
        names = [tc.get('name') for tc in tcs]
        return {'observed_followed': False,'confidence':'high','reason': f'initial turn issued {len(tcs)} parallel tool calls: {names}','evidence_refs':[{'iteration':0,'tools':names}]}
    name = tcs[0].get('name')
    if name in data_tools:
        return {'observed_followed': False,'confidence':'high','reason': f'initial turn invoked data-retrieval tool {name}','evidence_refs':[{'iteration':0,'tool':name}]}
    return {'observed_followed': True,'confidence':'low','reason': f'initial turn made single non-data tool call {name}','evidence_refs':[{'iteration':0,'tool':name}]}
