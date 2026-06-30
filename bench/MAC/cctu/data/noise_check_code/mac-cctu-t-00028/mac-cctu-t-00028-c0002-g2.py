def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    lines = [l for l in text.splitlines() if l.strip()]
    table_lines = [l for l in lines if l.strip().startswith('|') and l.strip().endswith('|')]
    if len(table_lines) < 2:
        return {'observed_followed': False, 'confidence':'high','reason':'no markdown table found','evidence_refs':[]}
    sep_found = any(re.match(r'^\s*\|?\s*:?-{2,}', l) and '|' in l and set(l.replace('|','').replace(':','').replace('-','').strip())==set() for l in table_lines)
    if not sep_found:
        return {'observed_followed': False, 'confidence':'medium','reason':'no header separator row','evidence_refs':[]}
    header = table_lines[0].lower()
    need = [('case', ['case']), ('defendant', ['defendant']), ('charge date', ['charge date','date'])]
    missing = [n for n,keys in need if not any(k in header for k in keys)]
    if missing:
        return {'observed_followed': False, 'confidence':'high','reason': 'missing columns: '+ ','.join(missing),'evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'high','reason':'markdown table with required columns','evidence_refs':[]}
