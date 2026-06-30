def evaluate(trace):
    import json, re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    text = resp
    m = re.search(r'\{[\s\S]*\}', text)
    if not m:
        return {'observed_followed': False,'confidence':'high','reason':'no JSON object found','evidence_refs':[]}
    try:
        data = json.loads(m.group(0))
    except Exception as e:
        return {'observed_followed': False,'confidence':'high','reason':f'invalid JSON: {e}','evidence_refs':[]}
    if not isinstance(data, dict) or not data:
        return {'observed_followed': False,'confidence':'high','reason':'not a non-empty object keyed by city','evidence_refs':[]}
    required = ['founding_year','dominant_architectural_style']
    citation_keys = ['source','sources','citation','citations','source_citations','references']
    missing = []
    for city, entry in data.items():
        if not isinstance(entry, dict):
            missing.append(f'{city}: not object'); continue
        for r in required:
            if r not in entry:
                missing.append(f'{city}:{r}')
        if not any(k in entry for k in citation_keys):
            missing.append(f'{city}:citations')
    if missing:
        return {'observed_followed': False,'confidence':'high','reason':'missing fields: '+'; '.join(missing[:5]),'evidence_refs':[]}
    return {'observed_followed': True,'confidence':'high','reason':'JSON dossier keyed by city with required fields and citations','evidence_refs':[]}
