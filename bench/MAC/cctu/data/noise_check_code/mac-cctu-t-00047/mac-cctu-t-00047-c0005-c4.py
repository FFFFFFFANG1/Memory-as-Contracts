def evaluate(trace):
    import re
    final=(trace.get('final_response') or '')
    tcs=trace.get('tool_calls') or []
    casualty_kw=r'(casualt|deaths?|killed|fatalit|injur|wounded|dead)'
    # detect if a casualty figure is issued in final response
    has_fig=False
    for m in re.finditer(r'([\d,]+)', final):
        start=max(0,m.start()-80); end=min(len(final),m.end()+80)
        ctx=final[start:end].lower()
        if re.search(casualty_kw, ctx):
            has_fig=True; break
    if not has_fig:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'No casualty figure detected in final response.', 'evidence_refs':[]}
    retrievers={'event_casualty_tracker','historical_event_data_retriever','election_results_analyzer','space_mission_identifier','weather_info_retriever'}
    used=[t.get('name') for t in tcs if t.get('name') in retrievers]
    distinct=set(used)
    if len(distinct)<2:
        return {'observed_followed': False, 'confidence':'high', 'reason': f'Only {len(distinct)} distinct retriever tool(s) used: {sorted(distinct)}.', 'evidence_refs':[]}
    # check that source identifiers (tool names) are logged in response
    logged=[t for t in distinct if t.lower() in final.lower()]
    if len(logged)<2:
        return {'observed_followed': False, 'confidence':'medium', 'reason': f'Fewer than two source identifiers logged in response; found {logged}.', 'evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'high', 'reason': f'Casualty figure cross-checked with {sorted(distinct)} and sources logged: {logged}.', 'evidence_refs':[]}
