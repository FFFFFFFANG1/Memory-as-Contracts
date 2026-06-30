def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    used_mt = any((tc.get('name') or '') == 'membership_tracker' for tc in tool_calls)
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    location_keywords = [
        'city','cities','town','village','country','countries','province','region',
        'state','capital','street','avenue','district','county','continent',
        'island','river','mountain','located in','based in','headquartered',
        'in the city of','in the town of','at the','near the'
    ]
    lowered = final.lower()
    hits = [k for k in location_keywords if re.search(r'\b'+re.escape(k)+r'\b', lowered)]
    if not used_mt:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'membership_tracker not invoked', 'evidence_refs': ['tool_calls']}
    if hits:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Possible location references: {hits}', 'evidence_refs': ['final_response']}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'membership_tracker used and no obvious location terms in final answer', 'evidence_refs': ['tool_calls','final_response']}
