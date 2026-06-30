import re, json
def evaluate(trace):
    resp = trace.get('final_response') or ''
    if not resp.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    # find last JSON object in response
    candidates = []
    for m in re.finditer(r'\{[\s\S]*\}', resp):
        candidates.append(m)
    if not candidates:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no JSON appendix found', 'evidence_refs': []}
    last = candidates[-1]
    tail = resp[last.end():].strip()
    if len(tail) > 50:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'JSON not at end of response', 'evidence_refs': [last.group(0)[:120]]}
    raw = last.group(0)
    try:
        data = json.loads(raw)
    except Exception:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'appendix not valid JSON', 'evidence_refs': [raw[:160]]}
    def flatten_keys(o, acc):
        if isinstance(o, dict):
            for k, v in o.items():
                acc.append(str(k).lower())
                flatten_keys(v, acc)
        elif isinstance(o, list):
            for v in o:
                flatten_keys(v, acc)
        return acc
    keys = flatten_keys(data, [])
    text = json.dumps(data).lower()
    has_year = any('year' in k for k in keys) or any(k in ('departure','departed','departure_year','year_of_departure') for k in keys)
    has_port = any('port' in k for k in keys) or any('origin' in k for k in keys)
    if has_year and has_port:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'JSON appendix includes year and originating port', 'evidence_refs': [raw[:200]]}
    missing = []
    if not has_year: missing.append('year of departure')
    if not has_port: missing.append('originating port')
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'appendix missing: ' + ', '.join(missing), 'evidence_refs': [raw[:200]]}
