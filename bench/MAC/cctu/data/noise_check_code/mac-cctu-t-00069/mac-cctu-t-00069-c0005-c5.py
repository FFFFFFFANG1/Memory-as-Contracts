def evaluate(trace):
    import json, re
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    first = calls[0].get('name')
    if first != 'event_host_locator':
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'first tool was {first}', 'evidence_refs': [{'tool': first}]}
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    text = resp
    m = re.search(r'```(?:json)?\s*(.*?)```', text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    try:
        parsed = json.loads(text)
    except Exception as e:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'response not valid JSON: {e}', 'evidence_refs': []}
    if not isinstance(parsed, dict):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'JSON is not a single object', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'event_host_locator called first; final response is a single JSON object', 'evidence_refs': []}
