import json
import re

def _find_json_object(text):
    text = (text or '').strip()
    if not text:
        return None
    candidates = [text]
    # try to extract object substrings
    starts = [i for i, ch in enumerate(text) if ch == '{']
    for s in starts:
        depth = 0
        for i in range(s, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    candidates.append(text[s:i+1])
                    break
    for cand in candidates:
        try:
            parsed = json.loads(cand)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None

def evaluate(trace):
    trace = trace or {}
    final = trace.get('final_response')
    if final is None or str(final).strip() == '':
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'missing final response', 'evidence_refs': []}
    final = str(final)
    parsed = _find_json_object(final)
    if parsed is None:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'final response is not a valid JSON object', 'evidence_refs': [{'field': 'final_response'}]}
    required = ['event', 'date', 'fatalities']
    keys = {str(k) for k in parsed.keys()}
    missing = [k for k in required if k not in keys]
    if missing:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'JSON object missing required keys: ' + ', '.join(missing), 'evidence_refs': [{'field': 'final_response', 'json_keys': sorted(keys)}]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': "JSON object contains 'event', 'date', and 'fatalities'", 'evidence_refs': [{'field': 'final_response', 'json_keys': sorted(keys)}]}
