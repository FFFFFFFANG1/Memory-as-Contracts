def evaluate(trace):
    import re
    resp = trace.get('final_response')
    if resp is None:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final_response','evidence_refs':[]}
    s = resp if isinstance(resp,str) else str(resp)
    stripped = s.strip()
    if not stripped:
        return {'observed_followed': False,'confidence':'high','reason':'empty response','evidence_refs':[]}
    if len(s) > 100:
        return {'observed_followed': False,'confidence':'high','reason':f'length {len(s)} exceeds 100 chars','evidence_refs':[]}
    if '\n' in stripped or '\r' in stripped:
        return {'observed_followed': False,'confidence':'high','reason':'response spans multiple lines','evidence_refs':[]}
    if re.search(r'<[^>]+>', stripped) or re.search(r'</[^>]+>', stripped):
        return {'observed_followed': False,'confidence':'high','reason':'delimiter/angle tag present','evidence_refs':[]}
    if re.search(r'\[[^\]]+\]|\{[^}]+\}', stripped):
        return {'observed_followed': False,'confidence':'medium','reason':'bracket-style delimiter present','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'high','reason':'within 100 chars, single line, no delimiter tags','evidence_refs':[]}
