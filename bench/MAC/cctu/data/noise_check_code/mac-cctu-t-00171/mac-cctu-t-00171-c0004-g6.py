def evaluate(trace):
    import re
    tools = ['artwork_artist_identifier','bibliographic_search_tool','biographical_info_retriever','biographical_residence_finder','historical_geography_associator','museum_dedication_finder','population_data_retriever','sports_award_tracker','tallest_building_finder','venue_capacity_checker']
    traj = trace.get('trajectory', []) or []
    # Find index of first tool call in trajectory
    first_tc_idx = None
    pre_text = ''
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if tcs:
            first_tc_idx = i
            break
        c = step.get('content') or ''
        if isinstance(c, str):
            pre_text += '\n' + c
    if first_tc_idx is None:
        # No tool calls at all; check if any discovery log exists in final or trajectory
        pre_text = '\n'.join([(s.get('content') or '') for s in traj if isinstance(s.get('content'), str)])
        if not pre_text.strip():
            return {'observed_followed': None, 'confidence':'unknown','reason':'No pre-tool-call content and no tool calls','evidence_refs':[]}
    low = pre_text.lower()
    tools_mentioned = [t for t in tools if t.lower() in low]
    # Heuristic for schema/input documentation
    schema_terms = ['input', 'parameter', 'argument', 'schema', 'arg']
    has_schema = any(term in low for term in schema_terms)
    discovery_terms = ['discovery log','available tools','tool list','tools:','tool inventory','enumeration']
    has_discovery = any(term in low for term in discovery_terms)
    all_listed = len(tools_mentioned) == len(tools)
    if all_listed and has_schema and (has_discovery or pre_text.count(':') >= len(tools)):
        return {'observed_followed': True, 'confidence':'high','reason':f'Pre-call log lists all {len(tools)} tools with input/schema docs','evidence_refs':[]}
    if not tools_mentioned:
        return {'observed_followed': False, 'confidence':'high','reason':'No tool enumeration found before first tool call','evidence_refs':[]}
    return {'observed_followed': False, 'confidence':'medium','reason':f'Found {len(tools_mentioned)}/{len(tools)} tools listed; schema_docs={has_schema}','evidence_refs':[]}
