def evaluate(trace):
    import re
    tools = ['election_result_fetcher','historical_event_search','historical_figure_identifier','maritime_incident_finder','political_event_retriever','political_leadership_tracker']
    traj = trace.get('trajectory') or []
    calls = trace.get('tool_calls') or []
    first_call_idx = None
    pre_text = ''
    for i, step in enumerate(traj):
        tc = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tc:
            first_call_idx = i
            break
        pre_text += '\n' + str(content)
    if first_call_idx is None:
        pre_text = '\n'.join(str(s.get('content') or '') for s in traj)
        pre_text += '\n' + str(trace.get('final_response') or '')
    low = pre_text.lower()
    mentioned = [t for t in tools if t.lower() in low]
    enumerated = len(mentioned) >= len(tools)
    rank_signals = ['rank','ranking','most relevant','relevance','order of relevance','prioriti','1.','2.','first','second']
    has_rank = any(s in low for s in rank_signals)
    if not pre_text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'No pre-tool reasoning text available.','evidence_refs':[]}
    if enumerated and has_rank:
        return {'observed_followed': True, 'confidence':'high','reason':f'All {len(tools)} tools enumerated with ranking signals before any retrieval.','evidence_refs':[]}
    if not enumerated:
        return {'observed_followed': False, 'confidence':'high','reason':f'Only {len(mentioned)}/{len(tools)} tools enumerated before first tool call.','evidence_refs':[]}
    return {'observed_followed': False, 'confidence':'medium','reason':'Tools enumerated but no clear ranking by topical relevance found.','evidence_refs':[]}
