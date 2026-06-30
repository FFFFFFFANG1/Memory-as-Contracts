def evaluate(trace):
    import json, re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    if not (resp.startswith('[') and resp.endswith(']')):
        return {'observed_followed': False, 'confidence':'high','reason':'response not wrapped solely as JSON array','evidence_refs':[resp[:120]]}
    try:
        data = json.loads(resp)
    except Exception as e:
        return {'observed_followed': False, 'confidence':'high','reason':f'invalid JSON: {e}','evidence_refs':[resp[:120]]}
    if not isinstance(data, list) or not data:
        return {'observed_followed': False, 'confidence':'high','reason':'top-level not a non-empty array','evidence_refs':[]}
    parent_keys = {'parent','dependency_parent','depends_on','dependencies','parent_id','parents'}
    missing = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            return {'observed_followed': False, 'confidence':'high','reason':f'element {i} not an object','evidence_refs':[str(item)[:80]]}
        keys = {k.lower() for k in item.keys()}
        if not (keys & parent_keys):
            missing.append(i)
    if missing:
        return {'observed_followed': False, 'confidence':'high','reason':f'subtasks missing dependency parent tag at indices {missing}','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'high','reason':'JSON array of subtasks with dependency parent tags, no surrounding prose','evidence_refs':[]}
