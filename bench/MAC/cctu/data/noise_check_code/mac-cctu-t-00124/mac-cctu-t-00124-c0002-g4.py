def evaluate(trace):
    import re
    tcs = trace.get('tool_calls', []) or []
    date_calls = [t for t in tcs if t.get('name') == 'historical_event_date_tool']
    if not date_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'historical_event_date_tool not used', 'evidence_refs': []}
    other_calls = [t for t in tcs if t.get('name') != 'historical_event_date_tool']
    if not other_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No corroborating tool calls made after retrieving historical dates', 'evidence_refs': [t.get('name') for t in tcs]}
    final = (trace.get('final_response') or '').lower()
    trajectory_text = ' '.join([str(s.get('content','')) for s in (trace.get('trajectory') or [])]).lower()
    combined = final + ' ' + trajectory_text
    cross_terms = ['cross-check', 'cross check', 'corroborat', 'verify', 'verified', 'confirm', 'discrepan', 'matches', 'consistent with', 'agrees with']
    has_cross = any(term in combined for term in cross_terms)
    if has_cross:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Date tool used and cross-checking language present alongside additional tool calls', 'evidence_refs': [t.get('name') for t in tcs]}
    return {'observed_followed': False, 'confidence': 'low', 'reason': 'No explicit cross-check/discrepancy reasoning found for retrieved dates', 'evidence_refs': [t.get('name') for t in tcs]}
