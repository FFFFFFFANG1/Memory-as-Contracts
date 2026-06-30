def evaluate(trace):
    import json
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    if not (resp.startswith('{') and resp.endswith('}')):
        return {'observed_followed': False, 'confidence':'high','reason':'response not a bare JSON object','evidence_refs':[resp[:80]]}
    try:
        obj = json.loads(resp)
    except Exception as e:
        return {'observed_followed': False, 'confidence':'high','reason':f'invalid JSON: {e}','evidence_refs':[resp[:80]]}
    if not isinstance(obj, dict):
        return {'observed_followed': False, 'confidence':'high','reason':'JSON is not an object','evidence_refs':[]}
    required = {'value','sources','confidence'}
    missing = required - set(obj.keys())
    if missing:
        return {'observed_followed': False, 'confidence':'high','reason':f'missing keys: {sorted(missing)}','evidence_refs':[list(obj.keys())]}
    return {'observed_followed': True, 'confidence':'high','reason':'bare JSON object with required keys','evidence_refs':[list(obj.keys())]}
