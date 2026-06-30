def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    maritime_tools = {'historical_maritime_event_finder','water_body_info_retriever'}
    maritime_calls = [c for c in calls if c.get('name') in maritime_tools]
    if not maritime_calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no maritime fact lookups found','evidence_refs':[]}
    # group by iteration to detect batches
    batches = {}
    for c in maritime_calls:
        it = c.get('iteration')
        batches.setdefault(it, []).append(c)
    # any solo (non-parallel) maritime call means not batched parallel
    solo = [it for it,b in batches.items() if len(b) < 2]
    if solo:
        return {'observed_followed': False,'confidence':'high','reason':f'maritime lookups not in parallel batches at iterations {solo}','evidence_refs':[]}
    final = trace.get('final_response') or ''
    # find footer area - last ~30% or after a separator
    footer = final
    for sep in ['\n---','Footer:','Audit','audit']:
        idx = final.rfind(sep)
        if idx != -1:
            footer = final[idx:]
            break
    else:
        footer = final[-400:]
    nums = re.findall(r'\d+', footer)
    n_batches = len(batches)
    if len(nums) < n_batches:
        return {'observed_followed': False,'confidence':'medium','reason':f'expected {n_batches} numerical audit ids in footer, found {len(nums)}','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'medium','reason':'parallel batched maritime calls with numerical audit ids in footer','evidence_refs':[]}
