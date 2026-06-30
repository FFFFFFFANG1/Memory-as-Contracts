import json
import re

def _parse_json_object(text):
    text = (text or '').strip()
    if not text:
        return None
    candidates = [text]
    # find balanced braces
    stack = []
    start = None
    for i, ch in enumerate(text):
        if ch == '{':
            if not stack:
                start = i
            stack.append(ch)
        elif ch == '}' and stack:
            stack.pop()
            if not stack and start is not None:
                candidates.append(text[start:i+1])
                start = None
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
    final = str(trace.get('final_response') or '')
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'missing final response', 'evidence_refs': []}
    parsed = _parse_json_object(final)
    if parsed is None:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'final response is not a valid JSON object', 'evidence_refs': [{'final_response_preview': final[:200]}]}
    keys = set(str(k) for k in parsed.keys())
    missing = [k for k in ('event', 'date') if k not in keys]
    if missing:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'JSON object missing required keys: {missing}', 'evidence_refs': [{'json_keys': sorted(keys)}]}
    # Check the response is essentially just the JSON object (single JSON object)
    stripped = final.strip()
    try:
        whole = json.loads(stripped)
        is_single = isinstance(whole, dict)
    except Exception:
        is_single = False
    if not is_single:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'response is not a single JSON object (extra content present)', 'evidence_refs': [{'json_keys': sorted(keys)}]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': "final response is a single JSON object with keys 'event' and 'date'", 'evidence_refs': [{'json_keys': sorted(keys)}]}
