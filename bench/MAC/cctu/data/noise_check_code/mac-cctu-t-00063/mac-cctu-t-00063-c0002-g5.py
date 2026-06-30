def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    lines = [l for l in text.splitlines() if '|' in l]
    if not lines:
        return {'observed_followed': False, 'confidence':'high','reason':'no markdown table found','evidence_refs':[]}
    header = None
    for i, l in enumerate(lines[:-1]):
        sep = lines[i+1]
        if re.match(r'^\s*\|?\s*:?-{2,}', sep) and '-' in sep:
            header = l
            break
    if header is None:
        return {'observed_followed': False, 'confidence':'high','reason':'no table header/separator','evidence_refs':[]}
    h = header.lower()
    needed = ['route','vessel','cargo']
    missing = [n for n in needed if n not in h]
    if missing:
        return {'observed_followed': False, 'confidence':'high','reason': 'missing columns: '+','.join(missing),'evidence_refs':[header]}
    return {'observed_followed': True, 'confidence':'high','reason':'markdown table with required columns','evidence_refs':[header]}
