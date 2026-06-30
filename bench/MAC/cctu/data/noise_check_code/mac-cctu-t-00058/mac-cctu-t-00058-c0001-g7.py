def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    final = (trace.get('final_response') or '').lower()
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    region_tools = {'individual_region_locator','institution_city_locator','cultural_information_retriever','musician_composer_finder','instrument_origin_locator','landmark_locator'}
    composers = {}
    # collect composer names referenced in region-related calls
    for c in calls:
        name = c.get('name','')
        args = c.get('arguments') or {}
        argstr = ' '.join(str(v) for v in (args.values() if isinstance(args,dict) else [args]))
        if name in region_tools:
            # heuristic: capture proper-noun-ish arg as composer key
            key = argstr.strip().lower()
            if key:
                composers.setdefault(key, []).append((c.get('index'), name))
    # Need at least 2 independent (distinct tool name) region verifications per composer
    verified = {}
    for k, lst in composers.items():
        distinct_tools = {n for _,n in lst}
        verified[k] = len(distinct_tools) >= 2
    dance_mentioned = bool(re.search(r'dance', final))
    if not composers:
        return {'observed_followed': None,'confidence':'low','reason':'no region verification calls detected','evidence_refs':[]}
    all_verified = all(verified.values())
    if dance_mentioned and not all_verified:
        return {'observed_followed': False,'confidence':'medium','reason':f'composers linked to dance without 2 independent regional verifications: {verified}','evidence_refs':[]}
    if all_verified:
        return {'observed_followed': True,'confidence':'medium','reason':'each composer has >=2 distinct region-related tool calls','evidence_refs':[]}
    return {'observed_followed': None,'confidence':'low','reason':'insufficient evidence','evidence_refs':[]}
