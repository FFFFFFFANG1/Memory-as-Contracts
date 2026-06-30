def evaluate(trace):
    import re
    geo_tools = {'artist_location_finder','building_info_retriever','city_feature_identifier','city_reputation_identifier','company_locator','historical_residence_finder','landmark_identifier'}
    other_geo = geo_tools - {'landmark_identifier'}
    text_parts = [trace.get('final_response','') or '']
    for step in trace.get('trajectory',[]) or []:
        c = step.get('content','')
        if c: text_parts.append(c)
    for tc in trace.get('tool_calls',[]) or []:
        args = tc.get('arguments',{})
        if isinstance(args, dict):
            for v in args.values():
                if isinstance(v,str): text_parts.append(v)
        res = tc.get('result','')
        if isinstance(res,str): text_parts.append(res)
    blob = ' '.join(text_parts).lower()
    canal_ref = bool(re.search(r'canal', blob))
    if not canal_ref:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'No canal heritage reference detected; constraint not triggered.', 'evidence_refs':[]}
    calls = trace.get('tool_calls',[]) or []
    ordered = sorted(calls, key=lambda t:(t.get('iteration',0), t.get('index',0)))
    first_geo_idx = None
    first_landmark_idx = None
    for i,tc in enumerate(ordered):
        name = tc.get('name')
        if name in geo_tools and first_geo_idx is None:
            first_geo_idx = i
        if name == 'landmark_identifier' and first_landmark_idx is None:
            first_landmark_idx = i
    if first_geo_idx is None:
        return {'observed_followed': None, 'confidence':'low', 'reason':'Canal heritage referenced but no geographic tool calls observed.', 'evidence_refs':[]}
    first_name = ordered[first_geo_idx].get('name')
    if first_name == 'landmark_identifier':
        return {'observed_followed': True, 'confidence':'high', 'reason':'landmark_identifier was invoked before any other geographic tool.', 'evidence_refs':[first_geo_idx]}
    return {'observed_followed': False, 'confidence':'high', 'reason': f'First geographic tool was {first_name}, not landmark_identifier.', 'evidence_refs':[first_geo_idx]}
