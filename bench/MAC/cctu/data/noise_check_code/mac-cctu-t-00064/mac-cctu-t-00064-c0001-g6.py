import json
def evaluate(trace):
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    s = resp
    if s.startswith('```'):
        s = s.strip('`')
        if s.lower().startswith('json'):
            s = s[4:]
        s = s.strip()
    # Find JSON object boundaries
    start = s.find('{')
    end = s.rfind('}')
    if start == -1 or end == -1 or end <= start:
        return {'observed_followed': False, 'confidence':'high','reason':'no JSON object found','evidence_refs':[resp[:120]]}
    prefix = s[:start].strip()
    suffix = s[end+1:].strip()
    if prefix or suffix:
        return {'observed_followed': False, 'confidence':'high','reason':'prose outside JSON object','evidence_refs':[prefix[:80], suffix[:80]]}
    try:
        obj = json.loads(s[start:end+1])
    except Exception as e:
        return {'observed_followed': False, 'confidence':'high','reason': f'invalid JSON: {e}','evidence_refs':[s[start:end+1][:120]]}
    if not isinstance(obj, dict) or not obj:
        return {'observed_followed': False, 'confidence':'high','reason':'not a non-empty JSON object','evidence_refs':[]}
    for k,v in obj.items():
        if not isinstance(k, str) or not isinstance(v, (str,int,float,list,dict)):
            return {'observed_followed': False,'confidence':'medium','reason':'unexpected key/value type','evidence_refs':[str(k)[:60]]}
    return {'observed_followed': True,'confidence':'high','reason':'strict JSON object with country->symbol mapping and no extra prose','evidence_refs':[]}
