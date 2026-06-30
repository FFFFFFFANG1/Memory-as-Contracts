def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    trajectory = trace.get('trajectory') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    tool_count = len(tool_names)
    round_count = len(trajectory)
    if round_count > 3:
        reasons.append('interaction rounds {round_count} above 3')
    if not re.search(r'\b\d{4}(?:[-/]\d{1,2}(?:[-/]\d{1,2})?)?\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b', response, flags=re.IGNORECASE):
        reasons.append('date not found in response')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
