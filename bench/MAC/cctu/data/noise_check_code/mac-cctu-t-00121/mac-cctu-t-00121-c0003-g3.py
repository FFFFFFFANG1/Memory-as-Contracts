def evaluate(trace):
    import re
    historical_tools = {
        'historical_event_finder','historical_event_finder_merged',
        'historical_event_information_tool','disaster_event_info_retriever',
        'aviation_incident_database','mountaineering_event_finder_v2',
        'historical_organization_info_retriever'
    }
    calls = trace.get('tool_calls') or []
    used = [c.get('name') for c in calls if c.get('name') in historical_tools]
    unique_used = set(used)
    final = (trace.get('final_response') or '')
    # detect a table (markdown pipe table or HTML table)
    has_pipe_table = bool(re.search(r'\n\s*\|.+\|.*\n\s*\|[\s\-:|]+\|', final))
    has_html_table = '<table' in final.lower()
    has_table = has_pipe_table or has_html_table
    # detect references to tool names in final (evidence logging)
    tools_mentioned = sum(1 for t in historical_tools if t in final)
    if len(calls) == 0:
        return {'observed_followed': None, 'confidence':'unknown','reason':'No tool calls in trace; cannot verify cross-verification.','evidence_refs':[]}
    if len(unique_used) < 3:
        return {'observed_followed': False, 'confidence':'high','reason':f'Only {len(unique_used)} distinct historical tools used; need >=3 for cross-verification.','evidence_refs':[{'tools_used':list(unique_used)}]}
    if not has_table:
        return {'observed_followed': False, 'confidence':'medium','reason':'No evidence table detected in final response.','evidence_refs':[]}
    if tools_mentioned < 3:
        return {'observed_followed': None, 'confidence':'low','reason':'Table present but fewer than 3 tool names referenced in evidence logging.','evidence_refs':[{'tools_mentioned':tools_mentioned}]}
    return {'observed_followed': True, 'confidence':'medium','reason':f'{len(unique_used)} historical tools used and evidence table present.','evidence_refs':[{'tools_used':list(unique_used)}]}
