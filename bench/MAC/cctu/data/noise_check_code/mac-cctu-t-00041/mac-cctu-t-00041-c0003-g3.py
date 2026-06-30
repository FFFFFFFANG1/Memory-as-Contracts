def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    names = [c.get('name','') for c in calls]
    required = {'historical_event_finder','political_leader_affiliation_finder'}
    lookup_tools = {'aviation_incident_finder','aviation_incident_retriever','geopolitical_event_finder','historical_event_info_retriever','historical_event_locator'}
    first_lookup_idx = None
    for i,n in enumerate(names):
        if n in lookup_tools:
            first_lookup_idx = i
            break
    verified_before = set()
    cutoff = first_lookup_idx if first_lookup_idx is not None else len(names)
    for i in range(cutoff):
        if names[i] in required:
            verified_before.add(names[i])
    if required.issubset(verified_before):
        return {'observed_followed': True,'confidence':'medium','reason':'both verification tools invoked before any lookup workflow tool','evidence_refs':[{'pre_lookup_names': names[:cutoff]}]}
    missing = list(required - verified_before)
    return {'observed_followed': False,'confidence':'medium','reason': f'missing verification before lookup: {missing}','evidence_refs':[{'names': names, 'first_lookup_idx': first_lookup_idx}]}
