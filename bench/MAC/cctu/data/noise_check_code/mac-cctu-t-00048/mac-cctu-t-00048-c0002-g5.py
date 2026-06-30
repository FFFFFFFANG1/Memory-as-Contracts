def evaluate(trace):
    import re
    final = (trace.get('final_response') or '').strip()
    tool_calls = trace.get('tool_calls') or []
    used = [tc for tc in tool_calls if tc.get('name') == 'lunar_eclipse_counter']
    if not used:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'lunar_eclipse_counter not invoked; cannot verify derivation', 'evidence_refs': []}
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty final response', 'evidence_refs': []}
    if re.fullmatch(r'-?\d+', final):
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'final response is a single integer', 'evidence_refs': [final]}
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'final response contains prose or non-integer content', 'evidence_refs': [final[:120]]}
