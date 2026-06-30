def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    tool_count = len(tool_names)
    allowed_tools = set(['financial_data_retriever', 'fiscal_year'])
    forbidden_used = sorted({name for name in tool_names if name and name not in allowed_tools})
    if forbidden_used:
        reasons.append('forbidden tools used: ' + ', '.join(forbidden_used[:5]))
    if response.strip() and not response.rstrip().endswith('.'):
        reasons.append('response does not end with period')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
