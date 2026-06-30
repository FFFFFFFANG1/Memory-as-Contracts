def evaluate(trace):
    import re
    tools = ['artwork_artist_identifier','bibliographic_search_tool','biographical_info_retriever','biographical_residence_finder','historical_geography_associator','museum_dedication_finder','population_data_retriever','sports_award_tracker','tallest_building_finder','venue_capacity_checker']
    resp = (trace.get('final_response') or '')
    calls = trace.get('tool_calls') or []
    if not resp.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    low = resp.lower()
    mentioned = [t for t in tools if t.lower() in low]
    # also accept reasonable humanized references; require most tools enumerated
    enumerated = len(mentioned) >= max(8, int(0.8*len(tools)))
    # check for line-per-tool style: count lines that contain a tool name
    lines = [l for l in resp.splitlines() if l.strip()]
    tool_lines = [l for l in lines if any(t.lower() in l.lower() for t in tools)]
    one_line_each = len(tool_lines) >= len(mentioned) and len(mentioned) >= 8
    # data retrieval deferred: no tool calls should have occurred
    deferred = len(calls) == 0
    followed = enumerated and one_line_each and deferred
    reason = f'mentioned={len(mentioned)}/{len(tools)}, tool_lines={len(tool_lines)}, tool_calls={len(calls)}'
    conf = 'high' if (enumerated and deferred) else 'medium'
    return {'observed_followed': bool(followed), 'confidence': conf, 'reason': reason, 'evidence_refs': []}
