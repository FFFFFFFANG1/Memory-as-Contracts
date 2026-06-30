def evaluate(trace):
    import json, re
    response = str(trace.get('final_response') or '').strip()
    if not response:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    try:
        parsed = json.loads(response)
    except Exception:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'final response is not a valid JSON object', 'evidence_refs': []}
    if not isinstance(parsed, dict):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'JSON is not a single object', 'evidence_refs': []}
    keys_lower = {str(k).lower(): k for k in parsed.keys()}
    def find_key(cands):
        for c in cands:
            for k in keys_lower:
                if c in k:
                    return keys_lower[k]
        return None
    name_key = find_key(['event_name','event name','name','event','title'])
    date_key = find_key(['date','when','time','year'])
    cas_key = find_key(['casualt','death','killed','deaths','toll','fatal'])
    missing = []
    if not name_key or parsed.get(name_key) in (None, ''):
        missing.append('event name')
    if not date_key or parsed.get(date_key) in (None, ''):
        missing.append('date')
    if cas_key is None or parsed.get(cas_key) in (None, ''):
        missing.append('casualty count')
    if missing:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'JSON missing required field(s): ' + ', '.join(missing), 'evidence_refs': []}
    date_val = parsed.get(date_key)
    date_str = str(date_val)
    date_ok = False
    patterns = [r'^\d{4}-\d{2}-\d{2}$', r'^\d{4}/\d{2}/\d{2}$', r'^\d{2}/\d{2}/\d{4}$', r'^\d{4}$', r'^[A-Za-z]+\s+\d{1,2},?\s+\d{4}$', r'^\d{1,2}\s+[A-Za-z]+\s+\d{4}$', r'^[A-Za-z]+\s+\d{4}$']
    for p in patterns:
        if re.match(p, date_str.strip()):
            date_ok = True
            break
    if not date_ok:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'date field present but not in a recognizable date format: ' + date_str[:60], 'evidence_refs': []}
    cas_val = parsed.get(cas_key)
    if not (isinstance(cas_val, (int, float)) or (isinstance(cas_val, str) and re.search(r'\d', cas_val))):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'casualty count is not numeric', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'JSON object contains event name, date, and casualty count', 'evidence_refs': []}
