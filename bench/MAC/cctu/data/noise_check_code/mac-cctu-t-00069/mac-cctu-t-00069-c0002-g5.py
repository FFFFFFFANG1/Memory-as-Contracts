def evaluate(trace):
    import re
    tcs = trace.get('tool_calls') or []
    final = (trace.get('final_response') or '').strip()
    if not tcs and not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no evidence', 'evidence_refs': []}
    first_ok = None
    if tcs:
        first_name = tcs[0].get('name')
        first_ok = (first_name == 'event_host_locator')
    ends_ok = bool(re.search(r'Host City:\s*[^\n]+\.\s*$', final))
    if first_ok is False:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'first tool was {tcs[0].get("name")}, not event_host_locator', 'evidence_refs': []}
    if not ends_ok:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'final response does not end with "Host City: [city]."', 'evidence_refs': []}
    if first_ok is None:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'no tool calls observed; cannot verify ordering', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'event_host_locator called first and final ends with Host City phrase', 'evidence_refs': []}
