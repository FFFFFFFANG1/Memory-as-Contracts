def evaluate(trace):
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    reasons = []
    if not response.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'empty final response', 'evidence_refs': []}
    if not response.lstrip().startswith('Scoping Notes:'):
        reasons.append('final response does not begin with literal prefix "Scoping Notes:"')
    if len(tool_calls) > 0:
        names = [str((tc or {}).get('name','')) for tc in tool_calls]
        reasons.append('tool calls were issued: ' + ', '.join(names))
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'response begins with "Scoping Notes:" and no tool calls were issued', 'evidence_refs': []}
