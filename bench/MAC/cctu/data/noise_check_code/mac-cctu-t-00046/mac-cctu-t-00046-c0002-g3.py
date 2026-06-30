def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls found','evidence_refs':[]}
    corp_related = {'corporate_event_tracker','historical_event_finder','historical_event_info_retriever','political_event_finder','political_event_search','political_event_tracker','incident_locator','trade_currency_analyzer','space_mission_event_finder','election_result_finder','political_appointment_finder'}
    used_corp = [c for c in calls if c.get('name') == 'corporate_event_tracker']
    if not used_corp:
        return {'observed_followed': None,'confidence':'unknown','reason':'no corporate_event_tracker call observed; cannot assess cross-check','evidence_refs':[]}
    distinct_tools = {c.get('name') for c in calls if c.get('name') in corp_related}
    independent = distinct_tools - {'corporate_event_tracker'}
    if len(independent) >= 2:
        return {'observed_followed': True,'confidence':'high','reason':f'corporate lookup cross-checked against {sorted(independent)}','evidence_refs':[]}
    if len(independent) == 1 and len(distinct_tools) >= 2:
        return {'observed_followed': False,'confidence':'medium','reason':'only one independent cross-check tool used','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'high','reason':'corporate event lookup not cross-checked against two independent tools','evidence_refs':[]}
