def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '').strip()
    if not response:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    low = response.lower()
    has_open = bool(re.search(r'<transportrecord(\s[^>]*)?>', low))
    has_close = '</transportrecord>' in low
    if not (has_open and has_close):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'missing <TransportRecord> envelope tags', 'evidence_refs': []}
    m = re.search(r'<transportrecord(?:\s[^>]*)?>(.*?)</transportrecord>', low, re.DOTALL)
    inner = m.group(1) if m else ''
    children = re.findall(r'<([a-zA-Z][\w:-]*)(?:\s[^>]*)?>', inner)
    children = [c for c in children if c.lower() != 'transportrecord']
    if len(children) < 1:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no child elements inside <TransportRecord>', 'evidence_refs': []}
    stripped = response.lstrip()
    if stripped.startswith('{') or stripped.startswith('['):
        try:
            import json
            json.loads(stripped)
            return {'observed_followed': False, 'confidence': 'high', 'reason': 'response appears to be JSON, not XML envelope', 'evidence_refs': []}
        except Exception:
            pass
    return {'observed_followed': True, 'confidence': 'high', 'reason': '<TransportRecord> envelope with child elements present', 'evidence_refs': []}
